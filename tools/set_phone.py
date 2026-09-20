#!/usr/bin/env python3
"""Update config.toml to set telegram phone number."""
import pathlib

p = pathlib.Path("/home/alexey/dev/kunipy/config.toml")
text = p.read_text()
text = text.replace('phone = ""', 'phone = "+79266347585"')
p.write_text(text)
print("Updated phone in config.toml")
