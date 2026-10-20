
import pytest
from services.calculs import calculer_metrage_pvc, calculer_surface_vitrage, calculer_total

def test_fenetre_deux_vantaux_exemple():
    r = calculer_metrage_pvc(1.2, 1.4, 2, 6000, 1)
    assert r["ml_cadre"] == pytest.approx(5.2)
    assert r["ml_horizontaux_ouvrants"] == pytest.approx(2.4)
    assert r["ml_verticaux_ouvrants"] == pytest.approx(5.6)
    assert r["ml_total"] == pytest.approx(13.2)
    assert r["cout_pvc_total"] == pytest.approx(79200)

def test_un_vantail_cadre_seul():
    r = calculer_metrage_pvc(1.2, 1.4, 1, 6000)
    assert r["ml_total"] == pytest.approx(5.2)
    assert r["cout_pvc_total"] == pytest.approx(31200)

def test_surface_vitrage():
    r = calculer_surface_vitrage(1.2, 1.4, 1)
    assert r["surface_totale"] == pytest.approx(1.68)

def test_total_taxe():
    r = calculer_total(1000, 500, taxe_active=True, taux_taxe=19)
    assert r["total_ttc"] == pytest.approx(1785)

def test_dimensions_invalides():
    with pytest.raises(ValueError):
        calculer_metrage_pvc(0, 1.4, 2, 6000)
