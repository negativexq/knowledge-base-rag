"""OCR'd pages are laid out from Tesseract's word groups, not MuPDF's OCR
blocks: those put everything on one visual line into a single block, so two
columns printed side by side (a directors list next to a bankers list) were
read as one mixed line. Lines are split at wide gaps and the page is cut
into bands and columns, so each column reads on its own; rows of three or
more aligned cells stay table rows, like on the text layer."""

import fitz

import app.parsing.pdf_parser as pdf_parser
from app.parsing.pdf_parser import extract_elements


def _line(x0: float, y0: float, text: str, height: float = 10.0, char: float = 5.0):
    return ((x0, y0, x0 + char * len(text), y0 + height), text)


def _texts(lines) -> list[str]:
    return [text for _, text in pdf_parser._ocr_layout(lines)]


def test_side_by_side_columns_are_read_one_after_the_other():
    lines = [
        _line(50, 90, "BOARD OF DIRECTORS"),
        _line(320, 90, "BANKERS"),
        _line(50, 104, "R.A. Shah - Chairman"),
        _line(320, 104, "State Bank of India"),
        _line(50, 118, "K.K. Modi - President"),
        _line(320, 118, "Bank of Baroda"),
        _line(50, 132, "Lalit Bhasin"),
        _line(320, 132, "Citibank N.A."),
    ]

    assert _texts(lines) == [
        "BOARD OF DIRECTORS R.A. Shah - Chairman K.K. Modi - President Lalit Bhasin",
        "BANKERS State Bank of India Bank of Baroda Citibank N.A.",
    ]


def test_word_groups_on_one_line_with_normal_spacing_stay_one_line():
    lines = [
        _line(44, 51, "GODFREY"),
        _line(94, 51, "PHILLIPS"),
        _line(149, 51, "INDIA"),
        _line(184, 51, "LIMITED"),
    ]

    assert _texts(lines) == ["GODFREY PHILLIPS INDIA LIMITED"]


def test_bands_separated_by_space_are_separate_paragraphs_in_page_order():
    lines = [
        _line(50, 40, "Annual Report 2023"),
        _line(50, 90, "Revenue grew in every region."),
        _line(50, 104, "Costs were flat."),
    ]

    assert _texts(lines) == [
        "Annual Report 2023",
        "Revenue grew in every region. Costs were flat.",
    ]


def test_aligned_rows_of_three_cells_stay_table_rows():
    lines = [
        _line(50, 100, "Item"),
        _line(200, 100, "Qty"),
        _line(350, 100, "Price"),
        _line(50, 114, "Paper"),
        _line(200, 114, "10"),
        _line(350, 114, "4.50"),
        _line(50, 128, "Ink"),
        _line(200, 128, "2"),
        _line(350, 128, "12.00"),
    ]

    assert _texts(lines) == ["Item | Qty | Price\nPaper | 10 | 4.50\nInk | 2 | 12.00"]


def test_prose_beside_a_table_reads_as_prose_then_table_rows():
    prose = [
        "The profit before taxation was higher at Rs. 79.60 crore",
        "as against Rs. 71.84 crore in the previous year. However,",
        "after providing for taxation and exceptional expense the",
        "net profit was lower than in the previous year.",
    ]
    table = [
        ("FINANCIAL RESULTS", "2002-2003", "2001-2002"),
        ("Gross Profit", "8873.49", "7995.12"),
    ]
    table += [("Less : Depreciation", "913.01", "811.28"), ("Net Profit", "4100.00", "3900.00")]
    lines = []
    for index, (sentence, (label, first, second)) in enumerate(zip(prose, table)):
        y = 100 + 14 * index
        lines += [
            _line(40, y, sentence, char=4.0),
            _line(320, y, label, char=4.0),
            _line(450, y, first, char=4.0),
            _line(520, y, second, char=4.0),
        ]

    assert _texts(lines) == [
        " ".join(prose),
        "FINANCIAL RESULTS | 2002-2003 | 2001-2002\n"
        "Gross Profit | 8873.49 | 7995.12\n"
        "Less : Depreciation | 913.01 | 811.28\n"
        "Net Profit | 4100.00 | 3900.00",
    ]


def test_full_width_text_right_above_two_columns_is_cut_off_first():
    lines = [
        _line(
            40, 86, "During the year under report the sales volume rose to 10593 million.", char=7.0
        ),
        _line(40, 100, "Profit before taxation was higher at Rs. 79.60 crore", char=4.0),
        _line(320, 100, "Gross Profit", char=4.0),
        _line(450, 100, "8873.49", char=4.0),
        _line(520, 100, "7995.12", char=4.0),
        _line(40, 114, "as against Rs. 71.84 crore in the previous year.", char=4.0),
        _line(320, 114, "Depreciation", char=4.0),
        _line(450, 114, "913.01", char=4.0),
        _line(520, 114, "811.28", char=4.0),
    ]

    assert _texts(lines) == [
        "During the year under report the sales volume rose to 10593 million.",
        "Profit before taxation was higher at Rs. 79.60 crore as against Rs. 71.84 crore "
        "in the previous year.",
        "Gross Profit | 8873.49 | 7995.12\nDepreciation | 913.01 | 811.28",
    ]


def test_right_aligned_number_columns_still_make_a_table():
    def number(right: float, y: float, text: str):
        return ((right - 5.0 * len(text), y, right, y + 10.0), text)

    lines = [
        _line(50, 100, "Gross Profit"),
        number(260, 100, "8873.49"),
        number(360, 100, "7995.12"),
        _line(50, 114, "Depreciation"),
        number(260, 114, "913.01"),
        number(360, 114, "811.28"),
        _line(50, 128, "Profit Brought Forward"),
        number(260, 128, "16233.07"),
        number(360, 128, "14377.30"),
    ]

    assert _texts(lines) == [
        "Gross Profit | 8873.49 | 7995.12\n"
        "Depreciation | 913.01 | 811.28\n"
        "Profit Brought Forward | 16233.07 | 14377.30"
    ]


def test_a_number_column_behind_a_wide_gutter_stays_with_its_labels():
    prose = [
        "The profit before taxation was higher at Rs. 79.60 crore",
        "as against Rs. 71.84 crore in the previous year. However,",
        "after providing for taxation and exceptional expense the",
    ]
    rows = [("Gross Profit", "8873.49", "7995.12"), ("Depreciation", "913.01", "811.28")]
    rows += [("Net Profit", "4100.00", "3900.00")]
    lines = []
    for index, (sentence, (label, first, second)) in enumerate(zip(prose, rows)):
        y = 100 + 14 * index
        lines += [
            _line(40, y, sentence, char=4.0),
            _line(300, y, label, char=4.0),
            _line(380, y, first, char=4.0),
            _line(500, y, second, char=4.0),
        ]
    # The last row of prose reaches into the label column, so the only
    # gutter left at the top level is the wide one before the last numbers.
    lines.append(
        _line(40, 142, "net profit was lower than in the previous year as shown here", char=5.5)
    )

    texts = _texts(lines)

    assert "Gross Profit | 8873.49 | 7995.12\nDepreciation | 913.01 | 811.28" in "\n".join(texts)


def test_overlapping_word_groups_on_a_line_are_joined_left_to_right():
    lines = [((408, 106, 440, 114), "State Bank"), ((436, 105, 467, 117), "of India")]

    assert _texts(lines) == ["State Bank of India"]


def test_scanned_two_column_page_becomes_two_elements(tmp_path, monkeypatch):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(
        fitz.Rect(0, 0, 50, 50), pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4))
    )
    path = tmp_path / "scan.pdf"
    doc.save(path)
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    monkeypatch.setattr(
        pdf_parser,
        "_ocr_lines",
        lambda page: [
            _line(50, 104, "Lalit Bhasin"),
            _line(320, 104, "State Bank of Hyderabad"),
            _line(50, 118, "Anup N. Kothari"),
            _line(320, 118, "Union Bank of India"),
        ],
    )

    elements = extract_elements(str(path))

    assert [e.text for e in elements] == [
        "Lalit Bhasin Anup N. Kothari",
        "State Bank of Hyderabad Union Bank of India",
    ]
    assert all("ocr:no_text_layer" in e.flags for e in elements)
