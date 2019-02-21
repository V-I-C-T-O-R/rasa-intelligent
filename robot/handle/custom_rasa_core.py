import json
import time
from _curses import error

import numpy as np
from flask import jsonify, request, abort
from rasa_core import events
from rasa_core.actions import action
from rasa_core.actions.action import UtterAction, Action
from rasa_core.channels import CollectingOutputChannel
from rasa_core.constants import DOCS_BASE_URL
from rasa_core.dispatcher import Dispatcher
from rasa_core.events import UserUttered, ActionExecuted, SlotSet, ReminderScheduled
from rasa_core.interpreter import NaturalLanguageInterpreter
from rasa_core.processor import MessageProcessor, scheduler
from rasa_core.run import load_agent
from rasa_core.trackers import EventVerbosity
from rasa_core.utils import AvailableEndpoints
from rasa_core_sdk.executor import ActionExecutor

from robot import logger
from robot.config.setting import Config
from robot.exception import ActionExecutionRejection


class RasaCore:

    def __init__(self):
        self.config = Config()
        self.endpoints = AvailableEndpoints.read_endpoints(self.config.RASA_CONFIG_ENDPOINTS_FILE)
        # self.interpreter = NaturalLanguageInterpreter.create(self.config.RASA_CONFIG_NLU_TRAIN_PACKAGE_NAME, self.endpoints.nlu)
        self.agent = load_agent(self.config.RASA_CONFIG_CORE_DIALOGUE_PACKAGE_NAME, interpreter=None, endpoints=self.endpoints)
        self.executor = ActionExecutor()
        self.executor.register_package(self.config.RASA_CONFIG_ENDPOINTS_ACTION_PACKAGE_NAME)
        self.message_processor = MessageProcessor(
            # self.interpreter,
            None,
            self.agent.policy_ensemble,
            self.agent.domain,
            self.agent.tracker_store,
            self.agent.nlg,
                action_endpoint=self.agent.action_endpoint,
                message_preprocessor=None)

    def handle_message(self,message):
        #message: UserMessage(text_message.get("text"),
        #             output_channel,
        #             sender_id)
        # out = CollectingOutputChannel()
        return self.message_processor.handle_message(message)

    # self.parse_data = {
    #     "intent": self.intent,
    #     "entities": self.entities,
    #     "text": text,
    # }
    def resolve_nlu_message(self,message):
        if message.parse_data:
            parse_data = message.parse_data
        else:
            parse_data = self.agent._parse_message(message)
        return parse_data


    def receive_nlu_message(self,message,parse_data):
        tracker = self.message_processor._get_tracker(message.sender_id)
        if tracker:
            tracker.update(UserUttered(message.text, parse_data["intent"],
                                       parse_data["entities"], parse_data,
                                       input_channel=message.input_channel))
            # store all entities as slots
            for e in self.agent.domain.slots_for_entities(parse_data["entities"]):
                tracker.update(e)
            self.predict_and_execute_next_action(message, tracker)
            self.message_processor._save_tracker(tracker)
            if isinstance(message.output_channel, CollectingOutputChannel):
                return message.output_channel.messages
            else:
                return None
        return None

    def predict_and_execute_next_action(self, message, tracker):
        dispatcher = Dispatcher(message.sender_id,
                                message.output_channel,
                                self.message_processor.nlg)
        # keep taking actions decided by the policy until it chooses to 'listen'
        should_predict_another_action = True
        num_predicted_actions = 0

        self.log_slots(tracker)
        # action loop. predicts actions until we hit action listen
        while (should_predict_another_action
               and self.should_handle_message(tracker)
               and num_predicted_actions < self.message_processor.max_number_of_predictions):
            # this actually just calls the policy's method by the same name
            probabilities, policy = self.message_processor._get_next_action_probabilities(tracker)
            max_index = int(np.argmax(probabilities))
            if self.message_processor.domain.num_actions <= max_index or max_index < 0:
                raise Exception(
                    "Can not access action at index {}. "
                    "Domain has {} actions.".format(max_index, self.message_processor.domain.num_actions))

            action = self.ask_for_action(self.message_processor.domain.action_names[max_index],self.message_processor.action_endpoint)
            confidence = probabilities[max_index]
            # action, policy, confidence = self.agent.predict_next_action(tracker)

            should_predict_another_action = self.run_action(action,
                                                             tracker,
                                                             dispatcher,
                                                             policy,
                                                             confidence)
            num_predicted_actions += 1

        if (num_predicted_actions == self.message_processor.max_number_of_predictions and
                should_predict_another_action):
            # circuit breaker was tripped
            if self.message_processor.on_circuit_break:
                # call a registered callback
                self.message_processor.on_circuit_break(tracker, dispatcher)

    def ask_for_action(self,action_name,action_endpoint):
        if action_name not in self.agent.domain.action_names:
            logger.warning("action not found")
            return None
        defaults = {a.name(): a for a in action.default_actions()}
        if action_name in defaults and action_name not in self.agent.domain.user_actions:
            return defaults.get(action_name)
        elif action_name.startswith("utter_"):
            return UtterAction(action_name)
        else:
            return RemoteAction(action_name, action_endpoint,self.executor)

    def should_handle_message(self, tracker):
        return (not tracker.is_paused() or
                tracker.latest_message.intent.get("name") ==
                self.agent.domain.restart_intent)

    def log_slots(self,tracker):
        # Log currently set slots
        slot_values = "\n".join(["\t{}: {}".format(s.name, s.value)
                                 for s in tracker.slots.values()])
        logger.debug("Current slot values: \n{}".format(slot_values))

    def run_action(self, action, tracker, dispatcher, policy=None, confidence=None):
        # events and return values are used to update
        # the tracker state after an action has been taken
        try:
            events = action.run(dispatcher, tracker, self.message_processor.domain)
        except Exception as e:
            logger.error("Encountered an exception while running action '{}'. "
                         "Bot will continue, but the actions events are lost. "
                         "Make sure to fix the exception in your custom "
                         "code.".format(action.name()), )
            logger.error(e, exc_info=True)
            events = []

        self.log_action_on_tracker(tracker, action.name(), events, policy,
                                    confidence)
        self.message_processor.log_bot_utterances_on_tracker(tracker, dispatcher)
        self.schedule_reminders(events, dispatcher)

        return self.message_processor.should_predict_another_action(action.name(), events)

    def schedule_reminders(self, events, dispatcher):
        # type: (List[Event], Dispatcher) -> None
        """Uses the scheduler to time a job to trigger the passed reminder.

        Reminders with the same `id` property will overwrite one another
        (i.e. only one of them will eventually run)."""

        if events is not None:
            for e in events:
                if isinstance(e, ReminderScheduled):
                    scheduler.add_job(self.message_processor.handle_reminder, "date",
                                      run_date=e.trigger_date_time,
                                      args=[e, dispatcher],
                                      id=e.name,
                                      replace_existing=True)

    def log_action_on_tracker(self, tracker, action_name, events, policy,
                               policy_confidence):
        # Ensures that the code still works even if a lazy programmer missed
        # to type `return []` at the end of an action or the run method
        # returns `None` for some other reason.
        if events is None:
            events = []

        logger.debug("Action '{}' ended with events '{}'".format(
                action_name, ['{}'.format(e) for e in events]))

        self.warn_about_new_slots(tracker, action_name, events)

        if action_name is not None:
            # log the action and its produced events
            tracker.update(ActionExecuted(action_name, policy,
                                          policy_confidence))

        for e in events:
            e.timestamp = time.time()
            tracker.update(e)

    def warn_about_new_slots(self, tracker, action_name, events):
        # these are the events from that action we have seen during training

        if action_name not in self.message_processor.policy_ensemble.action_fingerprints:
            return

        fp = self.message_processor.policy_ensemble.action_fingerprints[action_name]
        slots_seen_during_train = fp.get("slots", set())
        for e in events:
            if isinstance(e, SlotSet) and e.key not in slots_seen_during_train:
                s = tracker.slots.get(e.key)
                if s and s.has_features():
                    logger.warning(
                            "Action '{0}' set a slot type '{1}' that "
                            "it never set during the training. This "
                            "can throw of the prediction. Make sure to "
                            "include training examples in your stories "
                            "for the different types of slots this "
                            "action can return. Remember: you need to "
                            "set the slots manually in the stories by "
                            "adding '- slot{{\"{1}\": {2}}}' "
                            "after the action."
                            "".format(action_name, e.key, json.dumps(e.value)))

    def execute_actions(self,action_call):
        try:
            response = self.executor.run(action_call)
        except ActionExecutionRejection as e:
            result = {"error": str(e), "action_name": e.action_name}
            response = jsonify(result)
            response.status_code = 400
            return response

        return jsonify(response)

class Endpoints:
    def __init__(self):
        self.config = Config()
        self.endpoints = AvailableEndpoints.read_endpoints(self.config.RASA_CONFIG_ENDPOINTS_FILE)
        self.interpreter = NaturalLanguageInterpreter.create(self.config.RASA_CONFIG_NLU_TRAIN_PACKAGE_NAME,
                                                             self.endpoints.nlu)
        self.agent = load_agent(self.config.RASA_CONFIG_CORE_DIALOGUE_PACKAGE_NAME, interpreter=None,
                                endpoints=self.endpoints)
        self.executor = ActionExecutor()
        self.executor.register_package(self.config.RASA_CONFIG_ENDPOINTS_ACTION_PACKAGE_NAME)

        self.message_processor = MessageProcessor(
            # self.interpreter,
            None,
            self.agent.policy_ensemble,
            self.agent.domain,
            self.agent.tracker_store,
            self.agent.nlg,
            action_endpoint=self.agent.action_endpoint,
            message_preprocessor=self.agent.preprocessor)

    def execute_actions(self,action_call):
        try:
            response = self.executor.run(action_call)
        except ActionExecutionRejection as e:
            result = {"error": str(e), "action_name": e.action_name}
            response = jsonify(result)
            response.status_code = 400
            return response

        return jsonify(response)

    def event_verbosity_parameter(self,default_verbosity):
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

    def ask_for_action(self,action_name,action_endpoint):
        if action_name not in self.agent.domain.action_names:
            logger.warning("action not found")
            return None
        defaults = {a.name(): a for a in action.default_actions()}
        if action_name in defaults and action_name not in self.agent.domain.user_actions:
            return defaults.get(action_name)
        elif action_name.startswith("utter_"):
            return UtterAction(action_name)
        else:
            return RemoteAction(action_name, action_endpoint)


    def handle_actions(self,message,action_name):
        verbosity = self.event_verbosity_parameter(EventVerbosity.AFTER_RESTART)
        try:
            output_channel = CollectingOutputChannel()
            dispatcher = Dispatcher(message.sender_id,
                                    output_channel,
                                    self.agent.nlg)
            tracker = self.message_processor._get_tracker(message.sender_id)
            if tracker:
                #拿到action实例
                action = self.ask_for_action(action_name,self.message_processor.action_endpoint,self.ask_for_action)
                # action = self._get_action(action_name)
                self.message_processor._run_action(action, tracker, dispatcher)
                # save tracker state to continue conversation from this state
                self.message_processor._save_tracker(tracker)

            # retrieve tracker and set to requested state
            tracker = self.agent.tracker_store.get_or_create_tracker(message.sender_id)
            state = tracker.current_state(verbosity)
            return jsonify({"tracker": state,
                            "messages": output_channel.messages})

        except ValueError as e:
            return error(400, "ValueError", e)
        except Exception as e:
            return error(500, "ValueError",
                         "Server failure. Error: {}".format(e))

class RemoteAction(Action):
    def __init__(self, name, action_endpoint,executor):
        # type: (Text, Optional[EndpointConfig]) -> None
        self.config = Config()
        self._name = name
        self.action_endpoint = action_endpoint
        self.executor = executor

    def _action_call_format(self, tracker, domain):
        # type: (DialogueStateTracker, Domain) -> Dict[Text, Any]
        """Create the request json send to the action server."""
        from rasa_core.trackers import EventVerbosity

        tracker_state = tracker.current_state(EventVerbosity.ALL)

        return {
            "next_action": self._name,
            "sender_id": tracker.sender_id,
            "tracker": tracker_state,
            "domain": domain.as_dict()
        }

    @staticmethod
    def action_response_format_spec():
        """Expected response schema for an Action endpoint.

        Used for validation of the response returned from the
        Action endpoint."""
        return {
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "event": {"type": "string"}
                        }
                    }

                },
                "responses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                    }
                }
            },
        }

    def _validate_action_result(self, result):
        from jsonschema import validate
        from jsonschema import ValidationError

        try:
            validate(result, self.action_response_format_spec())
            return True
        except ValidationError as e:
            e.message += (
                ". Failed to validate Action server response from API, "
                "make sure your response from the Action endpoint is valid. "
                "For more information about the format visit "
                "{}/customactions/".format(DOCS_BASE_URL))
            raise e

    @staticmethod
    def _utter_responses(responses,  # type: List[Dict[Text, Any]]
                         dispatcher,  # type: Dispatcher
                         tracker  # type: DialogueStateTracker
                         ):
        # type: (...) -> None
        """Use the responses generated by the action endpoint and utter them.

        Uses the normal dispatcher to utter the responses from the action
        endpoint."""

        for response in responses:
            if "template" in response:
                kwargs = response.copy()
                del kwargs["template"]
                draft = dispatcher.nlg.generate(
                        response["template"],
                        tracker,
                        dispatcher.output_channel.name(),
                        **kwargs)
                if not draft:
                    continue

                del response["template"]
            else:
                draft = {}

            if "buttons" in response:
                if "buttons" not in draft:
                    draft["buttons"] = []
                draft["buttons"].extend(response["buttons"])
                del response["buttons"]

            draft.update(response)
            dispatcher.utter_response(draft)

    def run(self, dispatcher, tracker, domain):
        try:
            method = self.executor.actions[self.name()]
            response_data = method(dispatcher, tracker, domain)
            # self._validate_action_result(response_data)
        except Exception as e:
            raise Exception("Failed to execute custom action.")

        # events_json = response_data.get("events", [])
        events_json = []
        responses = []
        # responses = response_data.get("responses", [])

        self._utter_responses(responses, dispatcher, tracker)
        evts = events.deserialise_events(events_json)
        return evts

    def name(self):
        return self._name

