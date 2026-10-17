from sibo_bot.models import RestaurantReport
from sibo_bot.pdf import clean_text, render_report, report_filename


def test_clean_text():
    assert clean_text("") == ""
    assert clean_text(None) == ""
    assert clean_text("€15.00") == "EUR 15.00"
    assert clean_text("£20 / ¥3000") == "GBP 20 / JPY 3000"
    assert clean_text("Café Risotto") == "Café Risotto"
    assert clean_text("✓") == "?"


def test_render_city_report(city_report):
    pdf = render_report(city_report)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000


def test_render_location_report_with_notes_and_distances(location_report):
    assert render_report(location_report).startswith(b"%PDF-")


def test_render_empty_report():
    report = RestaurantReport(location_label="Nowhere", top_rated=[], cheapest=[])
    assert render_report(report).startswith(b"%PDF-")


def test_report_filename_is_safe(location_report):
    assert report_filename(location_report) == "SIBO_Guide_Wageningen_Centrum.pdf"
