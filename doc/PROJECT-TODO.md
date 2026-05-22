#LLMs: IGNORE THIS FILE#

for me:

- phase 3: test with findworkbot - coordinate through claude desktop
- add support to truncate response output with tail/grep/etc ?

for reuse:

- since claude code can write new code and execute it within the app container, what does this actually solve?
- make a pass on docs and errors to make them developer-friendly
  - all errors should point out where to fix (file & line/section, whenever possible)
- review for publishing
  - security - would it make sense to add authentication on the MCP endpoint, TLS, or is that overkill?
  - consider packaging to simplify installation/integration ?
- push to github
