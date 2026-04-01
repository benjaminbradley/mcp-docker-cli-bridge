#LLMs: IGNORE THIS FILE#

- the claude code container does not have python installed by default (it does have node) - use this for the example precommit hook script instead
- in addition to the timeout passed in the tool use call from the client, the commands.json config should include a maximum timeout globally, which can be customized per command
- clean up qualifiers which won't make sense in a finished product ("option b") - should only be a part of ADR
- request logger should log full request/response payloads for audit purposes (future: configurable yes/no), in addition to existing fields
- pass on docs and errors to make them developer-friendly - point out where to fix
- update README with usage documentation (its ok that it currently will not reflect the current functionality of the codebase, in this case I think it's a smart usage of our current context)
- consider if anything else from current context should be persisted before we reset the context window (make proposals, not changes yet)
