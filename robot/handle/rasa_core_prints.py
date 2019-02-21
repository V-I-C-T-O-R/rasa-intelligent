import logging
import os
import tempfile
import zipfile
from _curses import error
from functools import wraps

import rasa_core
import rasa_nlu
from flask import Blueprint, request, abort, Response, jsonify
from flask_cors import CORS, cross_origin
from rasa_core import constants, utils
from rasa_core.channels import CollectingOutputChannel, UserMessage
from rasa_core.evaluate import run_story_evaluation
from rasa_core.events import Event
from rasa_core.interpreter import NaturalLanguageInterpreter
from rasa_core.policies import PolicyEnsemble
from rasa_core.run import load_agent, create_http_input_channels
from rasa_core.server import ensure_loaded_agent, request_parameters
from rasa_core.trackers import EventVerbosity, DialogueStateTracker
from rasa_core.utils import AvailableEndpoints

from robot import app
from robot.config.setting import Config

logger = logging.getLogger(__name__)
robot_api = Blueprint('robot_api',__name__)

CORS(app, resources={r"/*": {"origins": "*"}})
cors_origins = None or []
__version__ = '0.11.6'
auth_token = None
config = Config
#初始化jwt参数
# JWTManager(app)

endpoints = AvailableEndpoints.read_endpoints(config.RASA_CONFIG_ENDPOINTS_FILE)
interpreter = NaturalLanguageInterpreter.create(config.RASA_CONFIG_NLU_TRAIN_PACKAGE_NAME, endpoints.nlu)
agent = load_agent(config.RASA_CONFIG_CORE_DIALOGUE_PACKAGE_NAME, interpreter=interpreter, endpoints=endpoints)
input_channels = create_http_input_channels('rest', None)
rasa_core.channels.channel.register(input_channels,app,agent.handle_message,route="/webhooks/")

@robot_api.route("/",
           methods=['GET', 'OPTIONS'])
@cross_origin(origins=cors_origins)
def hello():
    """Check if the server is running and responds with the version."""
    return "hello from Rasa Core: " + __version__

@robot_api.route("/version",
           methods=['GET', 'OPTIONS'])
@cross_origin(origins=cors_origins)
def version():
    """respond with the version number of the installed rasa core."""

    return jsonify({
        "version": __version__,
        "minimum_compatible_version": constants.MINIMUM_COMPATIBLE_VERSION
    })

# <sender_id> can be be 'default' if there's only 1 client
@robot_api.route("/conversations/<sender_id>/execute",
           methods=['POST', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
@ensure_loaded_agent(agent)
def execute_action(sender_id):
    request_params = request.get_json(force=True)
    action_to_execute = request_params.get("action", None)
    verbosity = event_verbosity_parameter(EventVerbosity.AFTER_RESTART)

    try:
        out = CollectingOutputChannel()
        agent.execute_action(sender_id,
                             action_to_execute,
                             out)

        # retrieve tracker and set to requested state
        tracker = agent.tracker_store.get_or_create_tracker(sender_id)
        state = tracker.current_state(verbosity)
        return jsonify({"tracker": state,
                        "messages": out.messages})

    except ValueError as e:
        return error(400, "ValueError", e)
    except Exception as e:
        logger.exception(e)
        return error(500, "ValueError",
                     "Server failure. Error: {}".format(e))

@robot_api.route("/conversations/<sender_id>/tracker/events",
           methods=['POST', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
@ensure_loaded_agent(agent)
def append_event(sender_id):
    """Append a list of events to the state of a conversation"""

    request_params = request.get_json(force=True)
    evt = Event.from_parameters(request_params)
    tracker = agent.tracker_store.get_or_create_tracker(sender_id)
    verbosity = event_verbosity_parameter(EventVerbosity.AFTER_RESTART)

    if evt:
        tracker.update(evt)
        agent.tracker_store.save(tracker)
        return jsonify(tracker.current_state(verbosity))
    else:
        logger.warning(
                "robot_apiend event called, but could not extract a "
                "valid event. Request JSON: {}".format(request_params))
        return error(400, "InvalidParameter",
                     "Couldn't extract a proper event from the request "
                     "body.",
                     {"parameter": "", "in": "body"})

@robot_api.route("/conversations/<sender_id>/tracker/events",
           methods=['PUT'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
@ensure_loaded_agent(agent)
def replace_events(sender_id):
    """Use a list of events to set a conversations tracker to a state."""

    request_params = request.get_json(force=True)
    verbosity = event_verbosity_parameter(EventVerbosity.AFTER_RESTART)

    tracker = DialogueStateTracker.from_dict(sender_id,
                                             request_params,
                                             agent.domain.slots)
    # will override an existing tracker with the same id!
    agent.tracker_store.save(tracker)
    return jsonify(tracker.current_state(verbosity))

@robot_api.route("/conversations",
           methods=['GET', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
def list_trackers():
    if agent.tracker_store:
        return jsonify(list(agent.tracker_store.keys()))
    else:
        return jsonify([])

@robot_api.route("/conversations/<sender_id>/tracker",
           methods=['GET', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
def retrieve_tracker(sender_id):
    """Get a dump of a conversations tracker including its events."""

    if not agent.tracker_store:
        return error(503, "NoTrackerStore",
                     "No tracker store available. Make sure to configure "
                     "a tracker store when starting the server.")

    # parameters
    default_verbosity = EventVerbosity.AFTER_RESTART

    # this is for backwards compatibility
    if "ignore_restarts" in request.args:
        ignore_restarts = utils.bool_arg('ignore_restarts', default=False)
        if ignore_restarts:
            default_verbosity = EventVerbosity.ALL

    if "events" in request.args:
        include_events = utils.bool_arg('events', default=True)
        if not include_events:
            default_verbosity = EventVerbosity.NONE

    verbosity = event_verbosity_parameter(default_verbosity)

    until_time = request.args.get('until', None)

    # retrieve tracker and set to requested state
    tracker = agent.tracker_store.get_or_create_tracker(sender_id)
    if not tracker:
        return error(503,
                     "NoDomain",
                     "Could not retrieve tracker. Most likely "
                     "because there is no domain set on the agent.")

    if until_time is not None:
        tracker = tracker.travel_back_in_time(float(until_time))

    # dump and return tracker

    state = tracker.current_state(verbosity)
    return jsonify(state)

@robot_api.route("/conversations/<sender_id>/respond",
           methods=['GET', 'POST', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
@ensure_loaded_agent(agent)
def respond(sender_id):
    request_params = request_parameters()

    if 'query' in request_params:
        message = request_params.pop('query')
    elif 'q' in request_params:
        message = request_params.pop('q')
    else:
        return error(400,
                     "InvalidParameter",
                     "Missing the message parameter.",
                     {"parameter": "query", "in": "query"})

    try:
        # Set the output channel
        out = CollectingOutputChannel()
        # Fetches the appropriate bot response in a json format
        responses = agent.handle_text(message,
                                      output_channel=out,
                                      sender_id=sender_id)
        return jsonify(responses)

    except Exception as e:
        logger.exception("Caught an exception during respond.")
        return error(500, "ActionException",
                     "Server failure. Error: {}".format(e))

@robot_api.route("/conversations/<sender_id>/predict",
           methods=['POST', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
@ensure_loaded_agent(agent)
def predict(sender_id):
    try:
        # Fetches the appropriate bot response in a json format
        responses = agent.predict_next(sender_id)
        return jsonify(responses)

    except Exception as e:
        logger.exception("Caught an exception during prediction.")
        return error(500, "PredictionException",
                     "Server failure. Error: {}".format(e))

@robot_api.route("/conversations/<sender_id>/messages",
           methods=['POST', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
@ensure_loaded_agent(agent)
def log_message(sender_id):
    request_params = request.get_json(force=True)
    try:
        message = request_params["message"]
    except KeyError:
        message = request_params.get("text")

    sender = request_params.get("sender")
    parse_data = request_params.get("parse_data")
    verbosity = event_verbosity_parameter(EventVerbosity.AFTER_RESTART)

    # TODO: implement properly for agent / bot
    if sender != "user":
        return error(500,
                     "NotSupported",
                     "Currently, only user messages can be passed "
                     "to this endpoint. Messages of sender '{}' "
                     "can not be handled. ".format(sender),
                     {"parameter": "sender", "in": "body"})

    try:
        usermsg = UserMessage(message, None, sender_id, parse_data)
        tracker = agent.log_message(usermsg)
        return jsonify(tracker.current_state(verbosity))

    except Exception as e:
        logger.exception("Caught an exception while logging message.")
        return error(500, "MessageException",
                     "Server failure. Error: {}".format(e))

@robot_api.route("/model",
           methods=['POST', 'OPTIONS'])
#@requires_auth(app, auth_token)
@cross_origin(origins=cors_origins)
def load_model():
    """Loads a zipped model, replacing the existing one."""

    if 'model' not in request.files:
        # model file is missing
        return error(400, "InvalidParameter",
                     "You did not supply a model as part of your request.",
                     {"parameter": "model", "in": "body"})

    model_file = request.files['model']

    logger.info("Received new model through REST interface.")
    zipped_path = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    zipped_path.close()
    model_directory = tempfile.mkdtemp()

    model_file.save(zipped_path.name)

    logger.debug("Downloaded model to {}".format(zipped_path.name))

    zip_ref = zipfile.ZipFile(zipped_path.name, 'r')
    zip_ref.extractall(model_directory)
    zip_ref.close()
    logger.debug("Unzipped model to {}".format(
            os.path.abspath(model_directory)))

    ensemble = PolicyEnsemble.load(model_directory)
    agent.policy_ensemble = ensemble
    logger.debug("Finished loading new agent.")
    return '', 204

@robot_api.route("/evaluate",
           methods=['POST', 'OPTIONS'])
#@requires_auth(app, auth_token)
@cross_origin(origins=cors_origins)
def evaluate_stories():
    """Evaluate stories against the currently loaded model."""
    tmp_file = rasa_nlu.utils.create_temporary_file(request.get_data(),
                                                    mode='w+b')
    use_e2e = utils.bool_arg('e2e', default=False)
    try:
        evaluation = run_story_evaluation(tmp_file, agent, use_e2e=use_e2e)
        return jsonify(evaluation)
    except ValueError as e:
        return error(400, "FailedEvaluation",
                     "Evaluation could not be created. Error: {}"
                     "".format(e))

@robot_api.route("/domain",
           methods=['GET', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
@ensure_loaded_agent(agent)
def get_domain():
    """Get current domain in yaml or json format."""

    accepts = request.headers.get("Accept", default="application/json")
    if accepts.endswith("json"):
        domain = agent.domain.as_dict()
        return jsonify(domain)
    elif accepts.endswith("yml"):
        domain_yaml = agent.domain.as_yaml()
        return Response(domain_yaml,
                        status=200,
                        content_type="application/x-yml")
    else:
        return error(406,
                     "InvalidHeader",
                     """Invalid accept header. Domain can be provided
                        as json ("Accept: application/json")
                        or yml ("Accept: application/x-yml").
                        Make sure you've set the appropriate Accept
                        header.""")

@robot_api.route("/finetune",
           methods=['POST', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
@ensure_loaded_agent(agent)
def continue_training():
    request.headers.get("Accept")
    epochs = request.args.get("epochs", 30)
    batch_size = request.args.get("batch_size", 5)
    request_params = request.get_json(force=True)
    sender_id = UserMessage.DEFAULT_SENDER_ID

    try:
        tracker = DialogueStateTracker.from_dict(sender_id,
                                                 request_params,
                                                 agent.domain.slots)
    except Exception as e:
        return error(400, "InvalidParameter",
                     "Supplied events are not valid. {}".format(e),
                     {"parameter": "", "in": "body"})

    try:
        # Fetches the appropriate bot response in a json format
        agent.continue_training([tracker],
                                epochs=epochs,
                                batch_size=batch_size)
        return '', 204

    except Exception as e:
        logger.exception("Caught an exception during prediction.")
        return error(500, "TrainingException",
                     "Server failure. Error: {}".format(e))

@robot_api.route("/status",
           methods=['GET', 'OPTIONS'])
@cross_origin(origins=cors_origins)
#@requires_auth(app, auth_token)
def status():
    return jsonify({
        "model_fingerprint": agent.fingerprint,
        "is_ready": agent.is_ready()
    })

@robot_api.route("/predict",
           methods=['POST', 'OPTIONS'])
#@requires_auth(app, auth_token)
@cross_origin(origins=cors_origins)
@ensure_loaded_agent(agent)
def tracker_predict():
    """ Given a list of events, predicts the next action"""

    sender_id = UserMessage.DEFAULT_SENDER_ID
    request_params = request.get_json(force=True)
    verbosity = event_verbosity_parameter(EventVerbosity.AFTER_RESTART)

    try:
        tracker = DialogueStateTracker.from_dict(sender_id,
                                                 request_params,
                                                 agent.domain.slots)
    except Exception as e:
        return error(400, "InvalidParameter",
                     "Supplied events are not valid. {}".format(e),
                     {"parameter": "", "in": "body"})

    policy_ensemble = agent.policy_ensemble
    probabilities, policy = \
        policy_ensemble.probabilities_using_best_policy(tracker,
                                                        agent.domain)

    scores = [{"action": a, "score": p}
              for a, p in zip(agent.domain.action_names, probabilities)]

    return jsonify({
        "scores": scores,
        "policy": policy,
        "tracker": tracker.current_state(verbosity)
    })

def ensure_loaded_agent(agent):
    """Wraps a request handler ensuring there is a loaded and usable model."""

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not agent.is_ready():
                return error(
                        503,
                        "NoAgent",
                        "No agent loaded. To continue processing, a "
                        "model of a trained agent needs to be loaded.",
                        help_url=_docs("/server.html#running-the-http-server"))

            return f(*args, **kwargs)

        return decorated
    return decorator

def _docs(sub_url):
    # type: (Text) -> Text
    """Create a url to a subpart of the docs."""
    return constants.DOCS_BASE_URL + sub_url

def event_verbosity_parameter(default_verbosity):
    event_verbosity_str = request.args.get(
            'include_events', default=default_verbosity.name).upper()
    try:
        return EventVerbosity[event_verbosity_str]
    except KeyError:
        enum_values = ", ".join([e.name for e in EventVerbosity])
        abort(error(404, "InvalidParameter",
                    "Invalid parameter value for 'include_events'. "
                    "Should be one of {}".format(enum_values),
                    {"parameter": "include_events", "in": "query"}))