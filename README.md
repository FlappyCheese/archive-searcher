# 🏛️ Internet Archive Paginated Search Tool

An interactive, paginated terminal browser for **Archive.org** with automatic virtual environment initialization.

---

## ✨ Features

- 📑 **Interactive Pagination**: Browse through millions of search results page by page.
- ⌨️ **Keyboard Navigation**:
  - `Enter` or `n` ➔ Next page
  - `p` ➔ Previous page
  - `g` ➔ Jump directly to any page number
  - `1 - 15` ➔ Instantly open that item in your default browser
  - `q` ➔ Start a new search
- ⚙️ **Automatic `.venv` Bootstrapping**: Automatically initializes `.venv` and installs `requests` and `rich` on the first launch.
- 🎨 **Rich UI**: High-contrast tables, colored media badges, and loading indicators.
- ⚡ **Lightweight API Calls**: Queries only 1 page at a time for lightning-fast loading.

---

## 🚀 How to Run

No manual environment setup or pip installs required. Just run:

```bash
python archive_search.py