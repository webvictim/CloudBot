from cloudbot import hook

shrugdude = u'\u00AF\_(\u30C4)_/\u00AF'

@hook.command(autohelp=False)
def shrug(message, conn):
    """shrug yo"""
    message(shrugdude)

@hook.command(autohelp=False)
def supson(message, conn):
    """SUP SON"""
    message(shrugdude)
