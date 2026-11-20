"""Explicit plugin mounting; no eval/exec or dynamic code from JSON."""
BUILDERS = {}
EDITORS = {}

def register_builder(name, function):
    if name in BUILDERS:raise ValueError('Builder already registered: '+name)
    BUILDERS[name]=function

def register_editor(name, function):
    if name in EDITORS:raise ValueError('Editor already registered: '+name)
    EDITORS[name]=function
