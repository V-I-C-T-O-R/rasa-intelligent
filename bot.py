import argparse
import warnings

from gevent.pywsgi import WSGIServer
from rasa_core import train
from rasa_core.agent import Agent
from rasa_core.interpreter import NaturalLanguageInterpreter, RasaNLUInterpreter
from rasa_core.policies import FallbackPolicy
from rasa_core.policies.keras_policy import KerasPolicy
from rasa_core.policies.memoization import MemoizationPolicy
from rasa_core.run import serve_application, load_agent
from rasa_core.training import online
from rasa_core.utils import AvailableEndpoints
from rasa_core_sdk.endpoint import endpoint_app


def train_nlu():
    from rasa_nlu.training_data import load_data
    from rasa_nlu.model import Trainer
    from rasa_nlu import config
    from rasa_nlu.components import ComponentBuilder
    import datetime

    starttime = datetime.datetime.now()
    configs = config.load("robot/config/nlu_model_config.yml")
    project = configs.get("project")
    model = configs.get("fixed_model_name")
    path = configs.get("path")
    num_threads = configs.get('num_threads')
    nlu_data_path = str(configs.get("data"))
    training_data = load_data(nlu_data_path)

    builder = ComponentBuilder(use_cache=True) # will cache components between pipelines (where possible)
    trainer = Trainer(configs, component_builder=builder)
    trainer.train(training_data, num_threads=num_threads)
    model_directory = trainer.persist(path=path, project_name=project, fixed_model_name=model)
    endtime = datetime.datetime.now()
    print('一共耗时', (endtime - starttime).seconds, 's')
    return model_directory


def train_core(domain_file="robot/config/domain.yml",
               model_path="robot/models/dialogue",
               training_data_file="robot/config/stories.md"):
    from rasa_core.featurizers import (MaxHistoryTrackerFeaturizer,
                                       BinarySingleStateFeaturizer)
    # fallback = FallbackPolicy(fallback_action_name="action_default_fallback",
    #                           core_threshold=0.9,
    #                           nlu_threshold=0.9)
    fallback = FallbackPolicy(fallback_action_name="action_default_custom",
                              core_threshold=0.8,
                              nlu_threshold=0.8)

    agent = Agent(domain_file,
                  policies=[MemoizationPolicy(max_history=5),
                            KerasPolicy(MaxHistoryTrackerFeaturizer(BinarySingleStateFeaturizer(), max_history=5)),fallback])
    training_data = agent.load_data(training_data_file)
    # 训练agent的策略policy
    agent.train(training_data, epochs=500)
    agent.persist(model_path)
    return agent


def run_online(domain_file="robot/config/domain.yml", stories_file="robot/config/stories.md", output_path="robot/models/dialogue",
               max_history=3, kwargs={"batch_size": 50, "epochs": 800, "max_training_samples": 300}):
    interpreter = RasaNLUInterpreter("models/ticket/nlu_bot")
    agent = train.train_dialogue_model(domain_file=domain_file,
                                       interpreter=interpreter,
                                       stories_file=stories_file,
                                       output_path=output_path,
                                       max_history=max_history,
                                       endpoints=AvailableEndpoints.read_endpoints("config/endpoints.yml"),
                                       kwargs=kwargs)

    online.run_online_learning(agent)


def endpoints(action='robot.actions.action'):
    edp_app = endpoint_app(action_package_name=action)

    http_server = WSGIServer(('0.0.0.0', 5001), edp_app)
    print("Starting action endpoint server...")
    http_server.start()
    print("Action endpoint is up and running. on {}"
          "".format(http_server.address))
    http_server.serve_forever()


def run():
    endpoints = AvailableEndpoints.read_endpoints('robot/config/endpoints.yml')
    interpreter = NaturalLanguageInterpreter.create('robot/models/current/nlu', endpoints.nlu)
    agent = load_agent("robot/models/dialogue", interpreter=interpreter, endpoints=endpoints)
    serve_application(agent, channel='rest')
    # serve_application(agent)

    return agent


def graph(domain_file="robot/config/domain.yml",
          training_data_file="robot/config/stories.md"):
    from rasa_core.featurizers import (MaxHistoryTrackerFeaturizer,
                                       BinarySingleStateFeaturizer)
    agent = Agent(domain_file,
                  policies=[MemoizationPolicy(max_history=6),
                            KerasPolicy(MaxHistoryTrackerFeaturizer(BinarySingleStateFeaturizer(), max_history=6))])

    agent.visualize(training_data_file, output_file='graph.png', max_history=6)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="starts the bot")

    parser.add_argument(
        "task",
        choices=["train-nlu", "train-core", 'endpoints', "run", "online-train"],
        help="what the bot should do - e.g. run or train?")
    task = parser.parse_args().task

    # decide what to do based on first parameter of the script
    if task == "train-nlu":
        train_nlu()
    elif task == "train-core":
        train_core()
    elif task == "endpoints":
        endpoints()
    elif task == "run":
        run()
    elif task == "online":
        run_online()
    else:
        warnings.warn("Need to pass either 'train-nlu','endpoints', 'train-core','run', or 'online' to use the script.")
        exit(1)
