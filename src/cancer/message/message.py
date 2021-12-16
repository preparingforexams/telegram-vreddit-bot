import abc
import dataclasses
import json


@dataclasses.dataclass
class Message(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def topic(cls) -> str:
        pass

    def serialize(self) -> str:
        return json.dumps(dataclasses.asdict(self))

    @classmethod
    def deserialize(cls, serialized: str):
        if not isinstance(serialized, str):
            raise ValueError(f"Not a str: {serialized}")

        return cls(**json.loads(serialized))
