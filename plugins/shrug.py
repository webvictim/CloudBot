from cloudbot import hook

shrugdude = u'\u00AF\_(\u30C4)_/\u00AF'

@hook.command('shrug', 'supson', autohelp=False)
def shrug(message, conn):
    """SUP SON"""
    message(shrugdude)
