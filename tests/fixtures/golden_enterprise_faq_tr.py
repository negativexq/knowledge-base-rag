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

# Özel Entegrasyonlar

Kurumsal müşteriler, Nimbus mühendislik ekibiyle birlikte özel API
entegrasyonları geliştirebilir. Bu tür projeler için minimum taahhüt
süresi 6 aydır ve ayrı bir entegrasyon ücreti uygulanır.

# IP Kısıtlaması

Yöneticiler, hesaba erişimi belirli bir IP adresi listesiyle
sınırlayabilir. IP kısıtlaması etkinleştirildiğinde, listede olmayan
bir adresten gelen tüm istekler (API dahil) 403 hatasıyla reddedilir.

# Çift Faktörlü Kimlik Doğrulama Zorunluluğu

Yöneticiler, tüm kurumsal hesap üyeleri için çift faktörlü kimlik
doğrulamayı (2FA) zorunlu kılabilir. Zorunluluk etkinleştirildikten
sonra 2FA kurmamış üyeler bir sonraki girişte otomatik olarak kurulum
akışına yönlendirilir, hesapları askıya alınmaz.

# Veri İşleme Sözleşmesi

Kurumsal müşteriler, GDPR uyumluluğu için bir Veri İşleme Sözleşmesi
(DPA) imzalayabilir. DPA, Yönetim Konsolu'ndaki Hukuki Belgeler
bölümünden dijital olarak imzalanır, ayrı bir kağıt süreç gerekmez.

# Kullanıcı Sağlama

Kurumsal paket, SCIM 2.0 protokolü üzerinden otomatik kullanıcı
sağlama (provisioning) destekler — bir kimlik sağlayıcıdan kullanıcı
eklendiğinde veya çıkarıldığında Nimbus hesabı otomatik güncellenir,
manuel senkronizasyon gerekmez.

# Loglama Saklama Süresi

Sistem logları (API çağrıları, hata izleri) 180 gün boyunca saklanır —
bu, denetim kaydının (audit log) 90 günlük saklama süresinden farklı
bir retention politikasıdır ve ayrı bir `/admin/system-logs` uç
noktasından erişilir.

# Destek Yanıt Süreleri

Kurumsal destek, kritik önem derecesindeki taleplere 1 saat içinde,
yüksek önem derecesindekilere 4 saat içinde yanıt verir. Standart
önem derecesindeki talepler için garanti edilen yanıt süresi 1 iş
günüdür.

# Alt Hesaplar

Bir kurumsal hesap, ayrı faturalandırma ve depolama kotalarına sahip
en fazla 10 alt hesap (sub-account) oluşturabilir. Alt hesaplar ana
hesabın SSO yapılandırmasını miras alır ama kendi rol/izin
atamalarına sahiptir.

# Dışa Aktarma Formatları

Toplu veri dışa aktarma, ZIP (orijinal dosya yapısı) veya tek bir
tar.gz arşivi (sıkıştırılmış, daha küçük indirme boyutu) formatında
istenebilir. ZIP formatı varsayılandır ve API çağrısında format
belirtilmezse kullanılır.
"""


def build_golden_enterprise_faq_tr(output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(GOLDEN_ENTERPRISE_FAQ_TR_TEXT)


if __name__ == "__main__":
    import sys

    build_golden_enterprise_faq_tr(
        sys.argv[1] if len(sys.argv) > 1 else "golden_enterprise_faq_tr.md"
    )
