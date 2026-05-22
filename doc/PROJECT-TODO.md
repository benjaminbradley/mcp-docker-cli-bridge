#LLMs: IGNORE THIS FILE#

for me:

- add support to truncate response output with tail/grep/etc
  this verifies that the publishing-prep changes didn't break anything needed for local development

for reuse:

- since claude code can write new code and execute it within the app container, what does this actually solve? need to do a security / threat model and write a clear statement to indicate when/how this is effective, and what can break it (e.g. running tests allows "arbitrary" code execution, while limiting it to lint/prettier should still be secure?)
- make a pass on docs and errors to make them developer-friendly
  - all errors should point out where to fix (file & line/section, whenever possible)
- review for publishing
  - security - would it make sense to add authentication on the MCP endpoint, TLS, or is that overkill?
- push to github
