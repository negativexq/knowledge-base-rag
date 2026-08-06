"""Builds the golden-set source Markdown doc: a fictional but internally-
consistent "Nimbus CLI" reference guide. Real, verifiable content — every
golden Q&A answer here is traceable to one exact heading path, the same
discipline golden_source.py (the PDF handbook) uses for (page, paragraph).

Written directly as a file (not generated programmatically like the PDF,
since Markdown is already plain text and needs no page-layout library).
"""

GOLDEN_MARKDOWN_TEXT = """\
# Kurulum

Nimbus CLI, `pip install nimbus-cli` komutuyla kurulur. Kurulum için
Python 3.9 veya üzeri gereklidir. Kurulumdan sonra `nimbus --version`
komutu kurulu sürümü gösterir.

## Sistem Gereksinimleri

Desteklenen işletim sistemleri: macOS 12+, Ubuntu 20.04+, Windows 10+.
Windows'ta CLI yalnızca PowerShell üzerinden resmi olarak desteklenir,
cmd.exe üzerinden çalıştırma denenmemiştir.

# Kimlik Doğrulama

`nimbus login` komutu bir tarayıcı penceresi açar ve OAuth akışıyla hesabı
CLI'a bağlar. Kimlik bilgileri `~/.nimbus/credentials` dosyasında, işletim
sisteminin anahtar zincirinde şifrelenmiş olarak saklanır.

## Token Süresi

Erişim token'ları 90 gün geçerlidir. Süre dolduğunda CLI otomatik olarak
yenileme token'ını kullanarak yeni bir erişim token'ı alır; kullanıcı
müdahalesi gerekmez.

# Senkronizasyon Komutları

`nimbus sync push <klasör>` yerel bir klasörü uzak depolamaya yükler.
`nimbus sync pull <klasör>` uzaktaki değişiklikleri yerel klasöre indirir.
Her iki komut da varsayılan olarak `--dry-run` bayrağı olmadan gerçek
değişiklik yapar.

## Çakışma Çözümü

Bir dosya hem yerelde hem uzakta değiştirilmişse, `sync push` varsayılan
olarak işlemi durdurur ve bir çakışma hatası gösterir. `--force-local`
bayrağı yerel sürümü zorla yükler; `--force-remote` uzak sürümü zorla
indirir.

# Sorun Giderme

`nimbus doctor` komutu yaygın kurulum sorunlarını (eksik bağımlılık,
geçersiz token, ağ erişimi) otomatik olarak kontrol eder ve her biri için
bir durum satırı yazdırır.

## Bağlantı Hataları

"Connection refused" hatası genellikle bir kurumsal proxy'nin CLI
trafiğini engellediği anlamına gelir. `NIMBUS_PROXY` ortam değişkeni
ayarlanarak bir proxy sunucusu belirtilebilir.
"""


def build_golden_markdown_source(output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(GOLDEN_MARKDOWN_TEXT)


if __name__ == "__main__":
    import sys

    build_golden_markdown_source(sys.argv[1] if len(sys.argv) > 1 else "golden_source.md")
