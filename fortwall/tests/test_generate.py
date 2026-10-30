"""Golden tests: renderers must reproduce the committed artifacts byte-for-byte."""

from pathlib import Path

import pytest

from fortwall_pool.generate import nginx, phpfpm, stage2out

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEMPLATES = FIXTURES / "templates"
EXPECTED = FIXTURES / "expected"


def test_nginx_conf_golden():
    assert nginx.render_nginx_conf((TEMPLATES / "nginx.conf").read_text(), 6) == (EXPECTED / "nginx.conf").read_text()


def test_sites_default_golden():
    assert nginx.render_sites_default((TEMPLATES / "default").read_text()) == (EXPECTED / "default").read_text()


def test_www_conf_golden():
    assert phpfpm.render_www_conf((TEMPLATES / "www.conf").read_text()) == (EXPECTED / "www.conf").read_text()


@pytest.mark.parametrize("i", [1, 2, 3, 4, 5, 6])
def test_pool_conf_golden(i):
    template = (TEMPLATES / "www.conf").read_text()
    assert phpfpm.render_pool_conf(template, i) == (EXPECTED / f"pool_{i}.conf").read_text()


@pytest.mark.parametrize("i", [1, 2, 3, 4, 5, 6])
def test_url_map_golden(i):
    p = EXPECTED / f"url_map_{i}.conf"
    urls = [ln.split(" unix:")[0] for ln in p.read_text().splitlines() if ln.strip()]
    assert nginx.render_url_map(urls, i) == p.read_text()


# --- Behavior-specific unit tests (independent of the golden fixtures) ---

def test_www_conf_preserves_max_children_quirk():
    # Original never rewrote max_children in www.conf; a "= 8" line stays "= 8".
    template = "[www]\npm.max_requests = 1\npm.max_children = 8\npm.max_spare_servers = 3\n"
    out = phpfpm.render_www_conf(template)
    assert "pm.max_requests = 0\n" in out
    assert "pm.max_children = 8\n" in out          # unchanged (quirk)
    assert "pm.max_spare_servers = 1\n" in out


def test_pool_conf_rewrites_children_and_socket():
    template = (
        "[www]\n"
        "listen = /opt/php-7.1/var/run/php/php7.1-fpm.sock\n"
        "pm.max_requests = 1\n"
        "pm.max_children = 8\n"
        "pm.max_spare_servers = 3\n"
    )
    out = phpfpm.render_pool_conf(template, 3)
    assert "[pool_3]\n" in out
    assert "listen = /opt/php-7.1/var/run/php/pool_3.sock\n" in out
    assert "pm.max_requests = 0\n" in out
    assert "pm.max_children = 1\n" in out          # pool DOES rewrite it
    assert "pm.max_spare_servers = 1\n" in out


def test_render_url_map_format():
    out = nginx.render_url_map(["/a.php", "/b.php"], 2)
    assert out == (
        "/a.php unix:/opt/php-7.1/var/run/php/pool_2.sock;\n"
        "/b.php unix:/opt/php-7.1/var/run/php/pool_2.sock;\n"
    )


def test_stage2out_roundtrips_urls_and_numbers():
    cats = [{"associated_numbers": [1, 2], "urls": ["/a", "/b"]}]
    assert stage2out.render_stage2_out(cats) == "/a 1 2\n/b 1 2\n"


def test_writers_create_files(tmp_path):
    cats = [{"associated_numbers": [1], "urls": ["/a"]}, {"associated_numbers": [2], "urls": ["/b"]}]
    written = nginx.write_url_maps(cats, tmp_path / "maps")
    assert [p.name for p in written] == ["url_map_1.conf", "url_map_2.conf"]
    assert (tmp_path / "maps" / "url_map_1.conf").exists()
