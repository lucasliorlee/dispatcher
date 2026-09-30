import curses
import json
from pathlib import Path


DATA_FILE = Path(__file__).with_name("stats.json")


def load_data():
    with DATA_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def draw_text(window, y, x, text, width, attributes=0):
    if y < 0 or y >= window.getmaxyx()[0] or width <= 0:
        return
    window.addnstr(y, x, str(text), width, attributes)


def draw_header(window, title, page_index, page_count):
    height, width = window.getmaxyx()
    window.attron(curses.color_pair(1))
    window.addnstr(0, 0, " TDS Stats Explorer ", max(0, width - 1))
    window.attroff(curses.color_pair(1))
    draw_text(window, 1, 2, f"{title}  [{page_index + 1}/{page_count}]", width - 4, curses.A_BOLD)
    draw_text(window, height - 1, 2, "Left/Right page  Up/Down table  Enter open  / search  q quit", width - 4, curses.A_DIM)


def choose_table(window, page_name, tables, page_index, page_count):
    selected = 0
    search = ""

    while True:
        window.erase()
        draw_header(window, page_name, page_index, page_count)
        height, width = window.getmaxyx()
        visible = [
            table for table in tables
            if not search or search.lower() in table.get("title", "").lower()
        ]
        draw_text(window, 3, 2, f"Tables: {len(visible)}    Filter: {search or '(none)'}", width - 4)

        if visible:
            selected = min(selected, len(visible) - 1)
            for index, table in enumerate(visible[: max(0, height - 6)]):
                attributes = curses.A_REVERSE if index == selected else 0
                draw_text(window, 5 + index, 4, table.get("title", "Untitled table"), width - 8, attributes)
        else:
            selected = 0
            draw_text(window, 5, 4, "No matching tables.", width - 8, curses.A_DIM)

        window.refresh()
        key = window.getch()
        if key in {ord("q"), 27}:
            return None
        if key == curses.KEY_LEFT:
            return -1
        if key == curses.KEY_RIGHT:
            return 1
        if key == curses.KEY_UP:
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN:
            selected = min(max(0, len(visible) - 1), selected + 1)
        elif key in {10, 13, curses.KEY_RIGHT} and visible:
            show_table(window, visible[selected])
        elif key == ord("/"):
            curses.echo()
            window.move(height - 1, 2)
            window.clrtoeol()
            draw_text(window, height - 1, 2, "Search: ", width - 4)
            search = window.getstr(height - 1, 10, max(1, width - 12)).decode(errors="replace")
            curses.noecho()
        elif key == ord("c"):
            search = ""


def show_table(window, table):
    row_offset = 0
    headers = table.get("headers", [])
    rows = table.get("rows", [])

    while True:
        window.erase()
        height, width = window.getmaxyx()
        draw_text(window, 0, 2, table.get("title", "Stats"), width - 4, curses.A_BOLD)
        draw_text(window, height - 1, 2, "Up/Down scroll  q/Esc back", width - 4, curses.A_DIM)

        column_count = max([len(headers)] + [len(row) for row in rows] + [1])
        column_width = max(8, (width - 4) // column_count)
        header_text = " | ".join(str(value) for value in headers)
        draw_text(window, 2, 2, header_text, width - 4, curses.A_REVERSE)

        visible_rows = max(1, height - 5)
        row_offset = min(row_offset, max(0, len(rows) - visible_rows))
        for index, row in enumerate(rows[row_offset : row_offset + visible_rows]):
            row_text = " | ".join(str(value) for value in row)
            draw_text(window, 4 + index, 2, row_text, width - 4)

        window.refresh()
        key = window.getch()
        if key in {ord("q"), 27, curses.KEY_LEFT, curses.KEY_ENTER}:
            return
        if key == curses.KEY_UP:
            row_offset = max(0, row_offset - 1)
        elif key == curses.KEY_DOWN:
            row_offset = min(max(0, len(rows) - visible_rows), row_offset + 1)


def main(window):
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
    data = load_data()
    pages = list(data.items())
    page_index = 0

    while True:
        page_name, tables = pages[page_index]
        result = choose_table(window, page_name, tables, page_index, len(pages))
        if result is None:
            return
        page_index = (page_index + result) % len(pages)


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except FileNotFoundError:
        print(f"Missing {DATA_FILE.name}. Run test.py first.")
