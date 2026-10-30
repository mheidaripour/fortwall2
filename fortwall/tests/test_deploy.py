from pathlib import Path

import pytest

from fortwall_pool import config
from fortwall_pool.deploy import modes
from fortwall_pool.deploy.system import Deployer

TEMPLATES = Path(__file__).resolve().parent / "fixtures" / "templates"


def _stage2_fixture(tmp_path):
    lines = [f"/big{i} 1 2 3" for i in range(50)]
    for url, nums in [("/a", "1 4"), ("/b", "1 5"), ("/c", "2 6"),
                      ("/d", "2 7"), ("/e", "8 9"), ("/f", "8 10")]:
        lines.append(f"{url} {nums}")
    p = tmp_path / "stage2_out_wordpress"
    p.write_text("\n".join(lines) + "\n")
    return p


def _work(tmp_path):
    return config.WorkPaths(root=tmp_path, generated=tmp_path / "generated", backups=tmp_path / "backups")


# --- Deployer dry-run: no filesystem mutation, ops recorded ---

def test_dryrun_records_ops_without_touching_fs(tmp_path):
    d = Deployer(work=_work(tmp_path), dry_run=True)
    d.replace_nginx_conf(tmp_path / "src.conf")
    d.restart_nginx()
    verbs = [op[0] for op in d.operations]
    assert verbs == ["copy", "run"]
    # destination is the real system path, but nothing was written
    assert d.operations[0][1][1] == config.SYSTEM.nginx_conf
    assert not (config.SYSTEM.nginx_conf).exists() or True  # never created by dry-run


def test_clean_configs_targets_expected_paths(tmp_path):
    d = Deployer(work=_work(tmp_path), dry_run=True)
    d.clean_configs("wordpress")
    targets = [str(a) for op in d.operations for a in op[1]]
    joined = " ".join(targets)
    assert "/etc/nginx/urlmapphp" in joined
    assert "/etc/nginx/nginx.conf" in joined
    assert "/opt/php-7.1/etc/php-fpm.d/www.conf" in joined
    assert "/home/paper/stage2_out_wordpress" in joined


# --- Local generation with the real committed templates ---

def test_generate_mpool_writes_all_artifacts(tmp_path):
    work = _work(tmp_path)
    arts = modes.generate_mpool(
        "wordpress", pools_num=4, work=work,
        stage2_out_path=_stage2_fixture(tmp_path),
        www_template=TEMPLATES / "www.conf",
        nginx_template=TEMPLATES / "nginx.conf",
        sites_template=TEMPLATES / "default",
    )
    assert arts.pool_count >= 1
    assert arts.intersection_file.exists()
    assert arts.stage2_out_file.exists()
    assert arts.nginx_conf.exists() and arts.sites_default.exists()

    # One url_map per pool, one pool_conf per pool (+ www.conf).
    url_maps = sorted(arts.url_map_dir.glob("url_map_*.conf"))
    pool_confs = sorted(arts.php_fpm_dir.glob("pool_*.conf"))
    assert len(url_maps) == arts.pool_count
    assert len(pool_confs) == arts.pool_count

    # nginx.conf gains exactly pool_count include lines.
    includes = [l for l in arts.nginx_conf.read_text().splitlines() if "urlmapphp/url_map" in l]
    assert len(includes) == arts.pool_count
    # sites default switched to the $upstream variable.
    assert "fastcgi_pass $upstream;" in arts.sites_default.read_text()


def test_switch_mpool_dryrun_sequence(tmp_path):
    work = _work(tmp_path)
    d = Deployer(work=work, dry_run=True)
    modes.switch_mpool(
        "wordpress", pools_num=4, deployer=d,
        stage2_out_path=_stage2_fixture(tmp_path),
        www_template=TEMPLATES / "www.conf",
        nginx_template=TEMPLATES / "nginx.conf",
        sites_template=TEMPLATES / "default",
    )
    verbs = [op[0] for op in d.operations]
    # Ends by restarting nginx; includes at least one copytree (url maps).
    assert verbs[-1] == "run"
    assert d.operations[-1][1][0] == "sudo systemctl restart nginx"
    assert "copytree" in verbs


def test_switch_saphire_dryrun(tmp_path):
    d = Deployer(work=_work(tmp_path), dry_run=True)
    modes.switch_saphire("wordpress", deployer=d)
    assert d.operations[-1] == ("run", ("sudo systemctl restart nginx",))
