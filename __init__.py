from . import draft_security, runtime_probe, runtime_channel, harvest_runtime


def register(ctx):
    draft_security.register(ctx)
    runtime_probe.register(ctx)
    runtime_channel.register(ctx)
    harvest_runtime.register(ctx)
