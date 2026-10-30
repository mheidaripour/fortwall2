from pathlib import Path

from fortwall_pool import report, cli

ROOT = Path(__file__).resolve().parents[1]

SAMPLE = """
Total number of URLs: 100
Category: 0 Percentage: 80.0
Category: 1 Percentage: 20.0
Intersection of the associated system call numbers for all the sets: {1, 2, 3}
Cluster 0 SP%: 90.0
Security Metric for Cluster 0(SN%): 85.0
Cluster 2: 5 urls
Cluster URL Percentage: 12.5
SP% 60.0
SN% 50.0
"""


def test_report_parse_text_extracts_fields():
    parsed = report.parse_text(SAMPLE)
    assert parsed["total_urls"] == 100
    assert parsed["category_percentages"] == [80.0, 20.0]
    assert parsed["intersection"] == {1, 2, 3}
    assert parsed["clusters"][0]["SP"] == 90.0
    assert parsed["clusters"][0]["SN"] == 85.0


def test_report_format_outputs_builds_tables():
    parsed = report.parse_text(SAMPLE)
    latex, md = report.format_outputs(parsed)
    assert any("Category 0" in row for row in md)
    assert any("Average" in row for row in md)
    assert latex  # non-empty LaTeX rows


def test_report_main_reads_file(tmp_path, capsys):
    f = tmp_path / "analysis.txt"
    f.write_text(SAMPLE)
    report.main([str(f)])
    out = capsys.readouterr().out
    assert "Markdown Table" in out
    assert "Intersection set:" in out


def test_cli_report_subcommand(tmp_path, capsys):
    f = tmp_path / "analysis.txt"
    f.write_text(SAMPLE)
    rc = cli.main(["report", str(f)])
    assert rc == 0
    assert "Markdown Table" in capsys.readouterr().out


def test_cli_baseline_subcommand(tmp_path, capsys):
    stage2 = tmp_path / "stage2_out_wordpress"
    stage2.write_text("/a 59 9\n/b 1 2 3 4 5\n")
    rc = cli.main([
        "baseline", "--file", str(stage2),
        "--syscall-table", str(ROOT / "data" / "syscall_table" / "unistd_64_.h"),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Average SP Rate:" in out
    assert "Max SN Rate:" in out


def test_cli_build_parser_requires_subcommand():
    import pytest
    with pytest.raises(SystemExit):
        cli.main([])
