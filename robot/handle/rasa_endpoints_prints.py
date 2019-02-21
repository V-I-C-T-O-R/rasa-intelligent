import logging

from flask import Blueprint, request, jsonify
from flask_cors import CORS, cross_origin
from rasa_core_sdk.executor import ActionExecutor

from robot import app
from robot.config.setting import Config
from robot.exception import ActionExecutionRejection

logger = logging.getLogger(__name__)
endpoints_api = Blueprint('endpoints_api',__name__)
config = Config
executor = ActionExecutor()
executor.register_package(config.RASA_CONFIG_ENDPOINTS_ACTION_PACKAGE_NAME)
cors_origins = None or []
CORS(app, resources={r"/*": {"origins": []}})

@endpoints_api.route("/health",
           methods=['GET', 'OPTIONS'])
@cross_origin(origins=cors_origins)
def health():
    """Ping endpoint to check if the server is running and well."""
    return jsonify({"status": "ok"})

@endpoints_api.route("/webhook",
           methods=['POST', 'OPTIONS'])
@cross_origin()
def webhook():
    """Webhook to retrieve action calls."""
    action_call = request.json
    try:
        response = executor.run(action_call)
    except ActionExecutionRejection as e:
        logger.error(str(e))
        result = {"error": str(e), "action_name": e.action_name}
        response = jsonify(result)
        response.status_code = 400
        return response

    return jsonify(response)