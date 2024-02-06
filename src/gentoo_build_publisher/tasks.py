"""Celery task definitions"""

import base64
import marshal
import types
from typing import Any, Callable

from celery import shared_task
from django.core import signing


@shared_task
def run(signed: str, *args: Any, **kwargs: Any) -> Any:
    """Decrypt signed function and run with the given args"""
    signer = signing.TimestampSigner()
    b64encoded = signer.unsign(signed)
    marshalled = base64.b64decode(b64encoded)
    code = marshal.loads(marshalled)
    func: Callable[..., Any] = types.FunctionType(code, {})

    return func(*args, **kwargs)  # pylint: disable=not-callable
