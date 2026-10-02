"""Discord command definitions and handlers, split by command domain."""
from . import base, skills, towers, enemies, handlers, tracker, dispatch

for _module in (base, skills, towers, enemies, handlers, tracker, dispatch):
    globals().update({k: v for k, v in vars(_module).items() if not k.startswith("__")})
