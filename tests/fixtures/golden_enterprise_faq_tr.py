"""Sprint 18: a second, real Turkish Markdown fixture — "Nimbus Kurumsal
SSS" (Enterprise FAQ) — written to expand the TR-content side of the
multilingual embedding benchmark's golden set past the original CLI
reference's 8 usable facts. Flat H1-only sections (no nesting), same
discipline as golden_api_reference_en.py's EN counterpart.
"""

GOLDEN_ENTERPRISE_FAQ_TR_TEXT = """\
# Tek Oturum Açma

Nimbus Kurumsal paket, SAML 2.0 ve OIDC üzerinden tek oturum açma (SSO)
destekler. SSO yapılandırması, kimlik sağlayıcının (Okta, Azure AD gibi)
metadata URL'sinin Nimbus Yönetim Konsolu'na eklenmesiyle tamamlanır.

# Denetim Kaydı

Her kurumsal hesap, giriş, dosya paylaşımı ve izin değişikliği gibi
olayları kaydeden bir denetim kaydına (audit log) sahiptir. Kayıtlar
90 gün boyunca saklanır ve `/admin/audit-log` API uç noktasından
JSON formatında dışa aktarılabilir.

# Veri Konumu

Kurumsal müşteriler, verilerinin saklanacağı bölgeyi (AB, ABD veya
Asya-Pasifik) hesap oluşturulurken seçebilir. Bölge seçimi hesap
oluşturulduktan sonra değiştirilemez; farklı bir bölgeye geçmek için
yeni bir hesap açılması ve verilerin manuel taşınması gerekir.

# Roller ve İzinler

Kurumsal paket beş yerleşik rol sunar: Sahibi, Yönetici, Üye, Misafir
ve Salt Okunur. Sadece Sahibi rolü faturalandırma bilgilerini
değiştirebilir; Yönetici rolü kullanıcı ekleyip çıkarabilir ama
faturalandırmaya erişemez.

# Hizmet Seviyesi Anlaşması

Kurumsal SLA, aylık %99.9 çalışma süresi garantisi verir. Bu eşiğin
altına düşülmesi durumunda müşteri, o ayki faturasının çalışma süresi
kaybıyla orantılı bir kısmı için kredi talep edebilir.

# Faturalandırma Döngüsü

Kurumsal faturalandırma varsayılan olarak yıllıktır, ama üç aylık
(quarterly) faturalandırma talep üzerine satış ekibiyle görüşülerek
etkinleştirilebilir. Yıllık faturalandırma, aylık faturalandırmaya göre
%15 indirim içerir.

# Veri Saklama Politikası

Silinen dosyalar, kalıcı olarak silinmeden önce 90 gün boyunca kurumsal
çöp kutusunda tutulur (standart hesaplardaki 30 günün aksine). Bir
yönetici, çöp kutusundaki herhangi bir dosyayı bu süre içinde geri
yükleyebilir.

# Yedekleme

Kurumsal veriler her gece otomatik olarak yedeklenir ve yedekler 35 gün
boyunca ayrı bir depolama bölgesinde saklanır. Manuel bir yedekten geri
yükleme talebi, destek ekibine bir talep açılarak yapılır ve genellikle
24 saat içinde tamamlanır.
"""


def build_golden_enterprise_faq_tr(output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(GOLDEN_ENTERPRISE_FAQ_TR_TEXT)


if __name__ == "__main__":
    import sys

    build_golden_enterprise_faq_tr(
        sys.argv[1] if len(sys.argv) > 1 else "golden_enterprise_faq_tr.md"
    )
