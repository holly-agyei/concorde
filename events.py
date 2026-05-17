import json
import queue
import time
from threading import Lock


_subscribers = []
_history = []
_lock = Lock()


def push_event(event_type, data=None):
    event = {
        "type": event_type,
        "data": data or {},
        "timestamp": time.time(),
    }
    with _lock:
        _history.append(event)
        del _history[:-80]
        subscribers = list(_subscribers)
    for subscriber in subscribers:
        subscriber.put(event)
    return event


def history():
    with _lock:
        return list(_history)


def subscribe():
    subscriber = queue.Queue()
    with _lock:
        _subscribers.append(subscriber)
        initial = list(_history)
    for event in initial:
        subscriber.put(event)
    return subscriber


def unsubscribe(subscriber):
    with _lock:
        if subscriber in _subscribers:
            _subscribers.remove(subscriber)


def encode_sse(event):
    return f"data: {json.dumps(event)}\n\n"
