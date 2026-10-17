You are correcting a transcript of a handwritten whiteboard. The transcript was read from a photo, so it contains spelling mistakes and misread letters.

Rules:
- Fix spelling mistakes and obvious misreadings. When a word is clearly one of the known project names or known todos below, use that exact spelling.
- Keep every line, in the same order. Never add, remove, merge or split lines.
- Keep the Markdown exactly: `#` and `##` headings, `- ` items, indentation, `Edges:` lines, arrows (`→`) and labels.
- Keep every checkbox exactly as it is: `- [x] ` stays ticked and `- [ ] ` stays empty.
- Do not rephrase, reword, summarise or add anything. Change only what is misspelled or misread.

Project name:
- The project name is the part of the title that names a project. For example, the project in "whiteBORAG architecture" is "whiteBORAG".
- If the title names one of the known projects, even misspelled, use that known name exactly.
- If the title ends in `(untitled)`, the project is `none`.
- If the title does not name a project, the project is `none`.

Output format:
- First line: `Project: ` followed by the project name, or `Project: none`.
- Second line: `---`
- Then the corrected Markdown, and nothing else. No commentary, no code fences.

Example. This is only an illustration of the format; never copy its content:

Known projects:
- GardenBot

Known todos:
- Order moisture sensor

Transcript:
# Gardn bot wiring
- [x] Order moistrue sensor
- [ ] Solder relay bord

Output:
Project: GardenBot
---
# GardenBot wiring
- [x] Order moisture sensor
- [ ] Solder relay board

Now correct this transcript.

Known projects:
{{PROJECTS}}

Known todos:
{{TODOS}}

Transcript:
{{TRANSCRIPT}}
