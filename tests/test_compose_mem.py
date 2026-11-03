import pathlib, re

def test_app_memory_limit_fits_the_16gb_vm():
    s = pathlib.Path(__file__).resolve().parents[1].joinpath("reports/deploy/docker-compose.yml").read_text()
    m = re.search(r"^\s+mem_limit:\s*(\d+)g\s*$", s, re.M)
    assert m and 8 <= int(m.group(1)) <= 14
