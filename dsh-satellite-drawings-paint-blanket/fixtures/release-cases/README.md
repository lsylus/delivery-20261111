# Curated release cases

These files are the compact inputs needed to understand and repeat the demonstrated paint workflow.

| File | Role |
| --- | --- |
| `simplified.step` | Primary flat-panel-with-blocks demonstration model used for paint recommendation, multi-face selection and drawing generation |
| `reference-paint.dwg` | Engineer-provided real paint drawing used as a visual and drafting reference |
| `engineering-requirements.docx` | Engineer-provided drawing requirements |
| `manifest.json` | Size, SHA256 and publication notes |

The original engineer archive is not committed because it is 116,928,155 bytes and duplicates extracted material. Its full assembly case is 670,820,444 bytes, exceeds GitHub's normal single-file limit and was explicitly excluded from the initial demo. The catch assembly was also removed from the demo because its import cost made iteration impractical.

Synthetic and derived automated cases remain under `fixtures/synthetic/` and `fixtures/real-derived/`.
