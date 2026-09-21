import pytest

from satcortex import profiles


@pytest.mark.parametrize("gb,erwartet_etwa", [(300, 10092), (100, 3364), (1000, 33640)])
def test_monatsbudget_wird_zu_tageswert(gb, erwartet_etwa):
    ist = profiles.upload_gb_pro_monat_zu_mib_pro_tag(gb)
    assert abs(ist - erwartet_etwa) <= 2


def test_null_bedeutet_unbegrenzt_und_bleibt_null():
    # Bitcoin Core versteht 0 als "kein Limit" -- das darf nicht verrechnet werden.
    assert profiles.upload_gb_pro_monat_zu_mib_pro_tag(0) == 0
    assert profiles.upload_gb_pro_monat_zu_mib_pro_tag(-5) == 0


def test_winziges_budget_wird_nicht_auf_null_gerundet():
    # Sonst waere aus "fast nichts" versehentlich "unbegrenzt" geworden.
    assert profiles.upload_gb_pro_monat_zu_mib_pro_tag(1) >= 1


def test_cache_ist_im_erstsync_groesser_als_im_betrieb():
    assert profiles.dbcache_mb(2500, True) > profiles.dbcache_mb(2500, False)


def test_cache_laesst_immer_luft_zur_speichergrenze():
    for grenze in (500, 1500, 2500, 4000, 8000):
        for sync in (True, False):
            assert profiles.dbcache_mb(grenze, sync) < grenze


def test_cache_bleibt_auch_bei_winziger_grenze_benutzbar():
    assert profiles.dbcache_mb(400, True) >= 300
    assert profiles.dbcache_mb(400, False) >= 150


def test_cache_waechst_nicht_ins_uferlose():
    assert profiles.dbcache_mb(64000, True) <= 4000


def test_zusammenfassung_erklaert_die_folge_der_wahl():
    begrenzt = profiles.zusammenfassung(2500, 300, 80)
    assert begrenzt["upload_unbegrenzt"] is False
    assert begrenzt["meldung_upload"] == "upload_begrenzt"

    unbegrenzt = profiles.zusammenfassung(2500, 0, 125)
    assert unbegrenzt["upload_unbegrenzt"] is True
    assert unbegrenzt["upload_mib_pro_tag"] == 0
