import logging
import json
import os
import re
import copy
from typing import Any, List, Text, Dict

import rasa.utils.io

from rasa.core import utils
from rasa.core.actions.action import (
    ACTION_BACK_NAME,
    ACTION_LISTEN_NAME,
    ACTION_RESTART_NAME,
)
from rasa.core.constants import USER_INTENT_BACK, USER_INTENT_RESTART
from rasa.core.domain import Domain
from rasa.core.events import ActionExecuted
from rasa.core.policies.policy import Policy
from rasa.core.trackers import DialogueStateTracker

logger = logging.getLogger(__name__)


class BFMappingPolicy(Policy):
    """Policy which maps intents directly to actions.

    Like RasaHQ's, except it looks for regex in the intent
    name, and always triggers the same premade action,
    meaning the model doesn't have to be retrained every
    time a new mapped intent is defined."""
    
    defaults = {
        'trigger': r'^map\..+'
    }

    def __init__(self, priority: int = 990, **kwargs: Any) -> None:
        super(BFMappingPolicy, self).__init__(priority=priority)
        self._load_params(**kwargs)

    def _load_params(self, **kwargs: Dict[Text, Any]) -> None:
        config = copy.deepcopy(self.defaults)
        config.update(kwargs)
        self.trigger = config.pop('trigger')
        self._train_params = config

    def train(
        self,
        training_trackers: List[DialogueStateTracker],
        domain: Domain,
        **kwargs: Any
    ) -> None:
        """Does nothing. This policy is deterministic."""

        pass

    def predict_action_probabilities(
        self, tracker: DialogueStateTracker, domain: Domain
    ) -> List[float]:
        logger.debug('Trigger: ' + self.trigger)
        """Predicts the assigned action.

        If the current intent is assigned to an action that action will be
        predicted with the highest probability of all policies. If it is not
        the policy will predict zero for every action."""

        prediction = [0.0] * domain.num_actions
        intent = tracker.latest_message.intent.get("name")
        match = re.search(self.trigger, intent)
        action = match.group(0) if match else None
        if tracker.latest_action_name == ACTION_LISTEN_NAME:
            if action:
                idx = domain.index_for_action('action_map')
                if idx is None:
                    logger.warning(
                        "action_map is not defined."
                    )
                else:
                    prediction[idx] = 1
            elif intent == USER_INTENT_RESTART:
                idx = domain.index_for_action(ACTION_RESTART_NAME)
                prediction[idx] = 1
            elif intent == USER_INTENT_BACK:
                idx = domain.index_for_action(ACTION_BACK_NAME)
                prediction[idx] = 1

            if any(prediction):
                logger.debug(
                    "The predicted intent '{}' is being "
                    " handled by BFMappingPolicy."
                    "".format(intent)
                )
        elif tracker.latest_action_name == action and action is not None:
            latest_action = tracker.get_last_event_for(ActionExecuted)
            assert latest_action.action_name == action

            if latest_action.policy == type(self).__name__:
                # this ensures that we only predict listen, if we predicted
                # the mapped action
                logger.debug(
                    "BFMappingPolicy has just been triggered, "
                    "so now returning to action_listen. "
                )

                idx = domain.index_for_action(ACTION_LISTEN_NAME)
                prediction[idx] = 1
        else:
            logger.debug(
                "Predicted intent is not handled by BFMappingPolicy."
            )
        return prediction

    def persist(self, path: Text) -> None:
        """Persists priority and trigger regex"""

        config_file = os.path.join(path, "bf_mapping_policy.json")
        meta = {
            "priority": self.priority,
            "trigger": self.trigger
        }
        rasa.utils.io.create_directory_for_file(config_file)
        utils.dump_obj_as_json_to_file(config_file, meta)

    @classmethod
    def load(cls, path: Text) -> "BFMappingPolicy":
        """Returns the class with the configured priority."""

        meta = {}
        if os.path.exists(path):
            meta_path = os.path.join(path, "bf_mapping_policy.json")
            if os.path.isfile(meta_path):
                meta = json.loads(rasa.utils.io.read_file(meta_path))

        return cls(**meta)
