# Poster Board — Music in Motion

Web version of the **Music in Motion** poster board (7-page layout).

## Contents

- **index.html** — Poster home: title, nav, and **Big Question** section only.
- **page1.html … page6.html** — One page per section: **Design Constraints**, **4 Key Design Patterns**, **Sensor Fusion Pipeline**, **HW / SW Components**, **Key Learnings**, **References**. Each page uses the section name as the heading and shows the matching image from `images/` (page1.png … page6.png).
- **icons.html** — All section icons at 10× size.
- **styles.css** — Styles for the poster layout.
- **images/** — Folder for poster images (`page1.png` … `page6.png`).

## Images

To show the original poster layout as images, export the first 6 pages of the PDF **Poster Board (layout).pdf** as images and place them in `images/` with these names:

| PDF page | Save as     | Section / page        |
|----------|-------------|------------------------|
| 1        | `page1.png` | Design Constraints    |
| 2        | `page2.png` | 4 Key Design Patterns |
| 3        | `page3.png` | Sensor Fusion Pipeline|
| 4        | `page4.png` | HW / SW Components    |
| 5        | `page5.png` | Key Learnings         |
| 6        | `page6.png` | References            |

You can export from Preview (macOS): open the PDF → File → Export as… → PNG, or use “Save as” per page. Other tools (e.g. ImageMagick `convert`, pdftoppm) work as long as the filenames match.

If an image is missing, the corresponding `<img>` will show a broken placeholder until the file is added.

## Viewing locally

Open `index.html` in a browser, or serve the folder with a local server:

```bash
# From project root
python -m http.server 8000
# Then open http://localhost:8000/posterboard/
```

Or from inside `posterboard`:

```bash
cd posterboard
python -m http.server 8080
# Open http://localhost:8080/
```
