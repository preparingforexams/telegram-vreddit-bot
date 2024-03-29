import abc
import dataclasses
import json


@dataclasses.dataclass
class Message(abc.ABC):
    chat_id: int
    message_id: int

    def serialize(self) -> bytes:
        return json.dumps(dataclasses.asdict(self)).encode("utf-8")

    @classmethod
    def deserialize(cls, serialized: bytes):
        if not isinstance(serialized, bytes):
            raise ValueError(f"Not a bytes: {serialized}")

        return cls(**json.loads(serialized.decode("utf-8")))
