You are given OCR text from a photo of a handwritten whiteboard. You cannot see the photo. Reconstruct the board in the format below using only this text. Don't invent arrows, boxes or checkboxes that the text doesn't show.

Rules:
- Keep the words exactly as the OCR gives them. Do not correct spelling, grammar or capitalisation.
- Drop OCR noise that is clearly not writing (stray symbols, repeated fragments).
- Write each piece of text once. Do not repeat content in more than one section.
- Never invent text: no headings, labels or items that are not in the OCR text.
- Output only Markdown. No commentary, no code fences.

Format:
- First line: `# ` followed by the board's title exactly as written. If the board has no title, write a short descriptive name followed by ` (untitled)`.
- If the board has a diagram (boxes or shapes joined by arrows), add a `## Diagram` section. List each box as a `- ` item, with boxes drawn inside another box indented under it. Then a line `Edges:` followed by one `- ` line per arrow: `- <from box> → <to box>`, adding `, labelled "<text>"` only when text is written on the arrow.
- Write any other text as `- ` items, indenting sub-points under their parent. If the list has a heading written on the board, put it on a `## ` line above the items. Otherwise put the items directly after the title.
- Write ticked boxes as `- [x] ` and empty boxes as `- [ ] `.
- Use `→` for every arrow.

Example. This is only an illustration of the format; never copy its content:

# Deploy steps

## Diagram
- Laptop
- Cloud (boundary box)
  - Server
Edges:
- Laptop → Server, labelled "ssh"

## Checklist
- [x] Build image
- [ ] Run migrations

The OCR text follows after the line `---`.
