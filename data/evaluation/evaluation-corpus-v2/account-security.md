# Hesap Güvenliği ve Kurtarma Standardı

Belge sahibi: Security Operations
Yürürlük: 2026-01-15
Kapsam: yönetici hesabı, MFA kurtarma ve IP izin listesi talepleri

Güvenlik hassasiyetli kurtarma taleplerinde doğrulanmış bir yönetici ve vaka referansı gerekir. Kimlik kontrolleri başarıyla tamamlandıktan sonra MFA kurtarma normalde 24 saat içinde sonuçlandırılır. Destek ekibi parola, tek kullanımlık kod veya kurtarma kodu istemez ve ifşa etmez.

Kurumsal yönetici IP izin listesini etkinleştirmişse liste dışında kalan istekler, API istekleri dâhil, reddedilir. İstisna talebi açmak izin listesini geçici olarak gevşetmez; görevli talebi güvenlik kuyruğuna yönlendirir ve doğrulama kanıtını vaka kaydına ekler.
