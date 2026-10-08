"""The audit gate's control: a pin with known advisories (CR 1, #103).

audit.yml's `canary` job runs `uv audit --script` on this file and passes only
when uv reports findings. starlette 1.0.0 carries five advisories (#103). Never
run or imported; the PEP 723 block below is the whole of its content.
"""

# /// script
# requires-python = ">=3.12"
# dependencies = ["starlette==1.0.0"]
# ///
