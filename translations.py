"""Traductions multilingues pour Goal Signal Bot."""

TRANSLATIONS = {
    "fr": {
        "start_title": "⚽ *SCORERADAR*",
        "start_separator": "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "start_desc": (
            "Recois des signaux Over en live avec un taux de reussite eleve.\n"
            "Acces au canal premium avec toutes les alertes en temps reel."
        ),
        "plan_trial": "🆓 *Essai Gratuit* — 3 jours d'acces complet",
        "plan_monthly": "💳 *Mensuel* — 9,99 EUR/mois",
        "plan_semestrial": "💎 *6 Mois* — 44,99 EUR (7,50 EUR/mois)",
        "plan_lifetime": "👑 *Lifetime* — 79,99 EUR, acces a vie",
        "choose_plan": "Choisis ton plan :",
        "referral_short": "Parraine et gagne du gratuit",
        "lang_short": "Changer de langue",
        "btn_trial": "🆓 Essai Gratuit — 3 jours",
        "btn_monthly": "💳 Mensuel — 9,99 EUR/mois",
        "btn_semestrial": "💎 6 Mois — 44,99 EUR (-25%)",
        "btn_lifetime": "👑 Lifetime — 79,99 EUR",
        "active_sub": "Tu as un abonnement actif : *{plan}*\nExpire : {expires}",
        "trial_activated": "✅ *Essai gratuit active — 3 jours*",
        "join_channel": "Rejoins le canal premium :",
        "enjoy": "Profites-en !",
        "trial_already_used": "Tu as deja utilise ton essai gratuit ou un abonnement.",
        "payment_not_configured": "Le paiement par carte n'est pas encore configure.\nContacte l'admin pour payer autrement.",
        "pay_now": "💳 Payer maintenant",
        "click_to_pay": "Clique pour payer par carte :",
        "payment_error": "Erreur lors de la creation du paiement. Reessaie plus tard.",
        "pay_card": "Carte bancaire",
        "pay_stars": "Telegram Stars",
        "choose_payment": "Choisis ton moyen de paiement :",
        "stars_invoice_desc": "Abonnement ScoreRadar — {plan}",
        "payment_received": "✅ *Paiement recu — {plan}*",
        "lifetime_thanks": "Acces a vie. Merci !",
        "expires_on": "Expire le : {date}",
        "sub_expired": "⏰ Ton abonnement a expire.\nTape /start pour te reabonner.",
        "alerts_off": "🔴 Alertes desactivees.\nTape /start pour les reactiver.",
        "loading_matches": "🔄 Chargement des matchs en direct...",
        "no_live_matches": "❌ Aucun match en direct actuellement.",
        "live_title": "⚽ *MATCHS EN DIRECT*",
        "matches_count": "📊 {count} matchs en cours",
        "leagues_title": "🏆 *CHAMPIONNATS*\n\nClique pour activer/desactiver :",
        "select_all": "🔄 Tout selectionner",
        "deselect_all": "🚫 Tout deselectionner",
        "sensitivity_title": "🔒 *SENSIBILITE*",
        "sensitivity_current": "Seuil actuel : *{value}/100*",
        "sensitivity_usage": (
            "Usage : `/sensitivity 50`\n"
            "• 40-50 = tres sensible (beaucoup d'alertes)\n"
            "• 60-70 = equilibre (recommande)\n"
            "• 80-90 = strict (peu d'alertes, haute confiance)"
        ),
        "sensitivity_updated": "✅ Seuil de confiance mis a jour : *{value}/100*",
        "sensitivity_invalid": "❌ Valeur invalide. Utilise un nombre entre 10 et 95.",
        "status_title": "📋 *STATUS*",
        "status_active": "🟢 Actif",
        "status_inactive": "🔴 Inactif",
        "status_threshold": "🔒 Seuil : {value}/100",
        "status_leagues": "🏆 Ligues ({count}) :",
        "status_more": "  ... et {count} autres",
        "status_scan": "⏱ Scan toutes les {interval}s",
        "expires_never": "Jamais",
        "lang_set": "🇫🇷 Langue reglée sur *Francais*",
        "lang_title": "🌍 *LANGUE / LANGUAGE*\n\nChoisis ta langue :",
        "referral_info": (
            "🤝 *PARRAINAGE*\n\n"
            "Ton lien : `{link}`\n\n"
            "👥 Filleuls payants : *{count}*\n"
            "🎯 Prochain palier : *{next_tier}* → {next_reward}\n\n"
            "📊 *Paliers :*\n"
            "• 3 filleuls → 1 mois gratuit\n"
            "• 5 filleuls → 3 mois gratuits\n"
            "• 10 filleuls → 6 mois gratuits\n"
            "• 20 filleuls → acces a vie"
        ),
        "referral_reward": "🎉 *Bravo !* Tu as atteint *{count} filleuls* !\nRecompense : *{reward}*",
        "referral_all_unlocked": "Tous les paliers debloques !",
        # --- Alertes ---
        "alert_title": "⚽ SIGNAL DE BUT DETECTE",
        "alert_live": "🟢 En direct · {elapsed}' · Score : {home_goals} – {away_goals}",
        "alert_analysis": "📊 ANALYSE EN DIRECT",
        "alert_minute": "⏱ Minute",
        "alert_score": "📈 Score",
        "alert_shots": "🎯 Tirs cadres",
        "alert_xg": "📉 xG",
        "alert_corners": "🔄 Corners",
        "alert_prematch": "📈 Pre-match",
        "alert_context": "🧠 CONTEXTE MATCH",
        "alert_signal": "🎯 SIGNAL DE TRADING",
        "alert_entry": "📍 Point d'entree",
        "alert_odds": "💰 Cote cible",
        "alert_window": "⏳ Intervalle but",
        "alert_probs": "📈 Probabilites",
        "alert_before_70": "├ Avant la 70e min",
        "alert_full_match": "└ Jusqu'a la fin",
        "alert_optimal": "💎 Pari optimal",
        "alert_next_goal": "→ Prochain but",
        "alert_aggressive": "⚡ Pari agressif",
        "alert_before_end": "→ But avant fin MT{half}",
        "alert_confidence": "🔒 Score de confiance",
        "ctx_xg_debt": "Le xG ({debt} au-dessus du score) indique que les occasions sont la mais le score ne suit pas encore.",
        "ctx_dominates": "{team} domine avec {possession} de possession.",
        "ctx_saves": "Les gardiens sont sollicites ({saves} arrets combines).",
        "ctx_shots": "Intensite offensive elevee ({shots} tirs cadres).",
        "ctx_no_goal": "Match sans but, la pression monte.",
        "ctx_tight_score": "Score serre en fin de match, les deux equipes poussent.",
        "ctx_peak": "Tranche {start}'-{end}' = pic historique de buts.",
    },
    "en": {
        "start_title": "⚽ *SCORERADAR*",
        "start_separator": "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "start_desc": (
            "Receive live Over signals with a high success rate.\n"
            "Access the premium channel with all real-time alerts."
        ),
        "plan_trial": "🆓 *Free Trial* — 3 days full access",
        "plan_monthly": "💳 *Monthly* — 9.99 EUR/month",
        "plan_semestrial": "💎 *6 Months* — 44.99 EUR (7.50 EUR/month)",
        "plan_lifetime": "👑 *Lifetime* — 79.99 EUR, forever",
        "choose_plan": "Choose your plan:",
        "referral_short": "Refer friends & earn free access",
        "lang_short": "Change language",
        "btn_trial": "🆓 Free Trial — 3 days",
        "btn_monthly": "💳 Monthly — 9.99 EUR/month",
        "btn_semestrial": "💎 6 Months — 44.99 EUR (-25%)",
        "btn_lifetime": "👑 Lifetime — 79.99 EUR",
        "active_sub": "You have an active subscription: *{plan}*\nExpires: {expires}",
        "trial_activated": "✅ *Free trial activated — 3 days*",
        "join_channel": "Join the premium channel:",
        "enjoy": "Enjoy!",
        "trial_already_used": "You have already used your free trial or have a subscription.",
        "payment_not_configured": "Card payment is not yet configured.\nContact the admin to pay otherwise.",
        "pay_now": "💳 Pay now",
        "click_to_pay": "Click to pay by card:",
        "payment_error": "Error creating payment. Please try again later.",
        "pay_card": "Credit card",
        "pay_stars": "Telegram Stars",
        "choose_payment": "Choose your payment method:",
        "stars_invoice_desc": "ScoreRadar subscription — {plan}",
        "payment_received": "✅ *Payment received — {plan}*",
        "lifetime_thanks": "Lifetime access. Thank you!",
        "expires_on": "Expires on: {date}",
        "sub_expired": "⏰ Your subscription has expired.\nType /start to resubscribe.",
        "alerts_off": "🔴 Alerts disabled.\nType /start to reactivate.",
        "loading_matches": "🔄 Loading live matches...",
        "no_live_matches": "❌ No live matches currently.",
        "live_title": "⚽ *LIVE MATCHES*",
        "matches_count": "📊 {count} matches in progress",
        "leagues_title": "🏆 *LEAGUES*\n\nClick to enable/disable:",
        "select_all": "🔄 Select all",
        "deselect_all": "🚫 Deselect all",
        "sensitivity_title": "🔒 *SENSITIVITY*",
        "sensitivity_current": "Current threshold: *{value}/100*",
        "sensitivity_usage": (
            "Usage: `/sensitivity 50`\n"
            "• 40-50 = very sensitive (many alerts)\n"
            "• 60-70 = balanced (recommended)\n"
            "• 80-90 = strict (few alerts, high confidence)"
        ),
        "sensitivity_updated": "✅ Confidence threshold updated: *{value}/100*",
        "sensitivity_invalid": "❌ Invalid value. Use a number between 10 and 95.",
        "status_title": "📋 *STATUS*",
        "status_active": "🟢 Active",
        "status_inactive": "🔴 Inactive",
        "status_threshold": "🔒 Threshold: {value}/100",
        "status_leagues": "🏆 Leagues ({count}):",
        "status_more": "  ... and {count} more",
        "status_scan": "⏱ Scan every {interval}s",
        "expires_never": "Never",
        "lang_set": "🇬🇧 Language set to *English*",
        "lang_title": "🌍 *LANGUAGE*\n\nChoose your language:",
        "referral_info": (
            "🤝 *REFERRAL*\n\n"
            "Your link: `{link}`\n\n"
            "👥 Paying referrals: *{count}*\n"
            "🎯 Next tier: *{next_tier}* → {next_reward}\n\n"
            "📊 *Tiers:*\n"
            "• 3 referrals → 1 free month\n"
            "• 5 referrals → 3 free months\n"
            "• 10 referrals → 6 free months\n"
            "• 20 referrals → lifetime access"
        ),
        "referral_reward": "🎉 *Congrats!* You reached *{count} referrals*!\nReward: *{reward}*",
        "referral_all_unlocked": "All tiers unlocked!",
        # --- Alerts ---
        "alert_title": "⚽ GOAL SIGNAL DETECTED",
        "alert_live": "🟢 Live · {elapsed}' · Score: {home_goals} – {away_goals}",
        "alert_analysis": "📊 LIVE ANALYSIS",
        "alert_minute": "⏱ Minute",
        "alert_score": "📈 Score",
        "alert_shots": "🎯 Shots on target",
        "alert_xg": "📉 xG",
        "alert_corners": "🔄 Corners",
        "alert_prematch": "📈 Pre-match",
        "alert_context": "🧠 MATCH CONTEXT",
        "alert_signal": "🎯 TRADING SIGNAL",
        "alert_entry": "📍 Entry point",
        "alert_odds": "💰 Target odds",
        "alert_window": "⏳ Goal window",
        "alert_probs": "📈 Probabilities",
        "alert_before_70": "├ Before 70th min",
        "alert_full_match": "└ Until full time",
        "alert_optimal": "💎 Optimal bet",
        "alert_next_goal": "→ Next goal",
        "alert_aggressive": "⚡ Aggressive bet",
        "alert_before_end": "→ Goal before end HT{half}",
        "alert_confidence": "🔒 Confidence score",
        "ctx_xg_debt": "xG ({debt} above score) indicates chances are there but the score hasn't followed yet.",
        "ctx_dominates": "{team} dominates with {possession} possession.",
        "ctx_saves": "Goalkeepers under pressure ({saves} combined saves).",
        "ctx_shots": "High offensive intensity ({shots} shots on target).",
        "ctx_no_goal": "Goalless match, pressure is building.",
        "ctx_tight_score": "Tight score late in the game, both teams pushing.",
        "ctx_peak": "{start}'-{end}' range = historical goal peak.",
    },
    "es": {
        "start_title": "⚽ *SCORERADAR*",
        "start_separator": "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "start_desc": (
            "Recibe senales Over en vivo con una alta tasa de exito.\n"
            "Acceso al canal premium con todas las alertas en tiempo real."
        ),
        "plan_trial": "🆓 *Prueba Gratis* — 3 dias de acceso completo",
        "plan_monthly": "💳 *Mensual* — 9,99 EUR/mes",
        "plan_semestrial": "💎 *6 Meses* — 44,99 EUR (7,50 EUR/mes)",
        "plan_lifetime": "👑 *Lifetime* — 79,99 EUR, acceso de por vida",
        "choose_plan": "Elige tu plan:",
        "referral_short": "Invita amigos y gana acceso gratis",
        "lang_short": "Cambiar idioma",
        "btn_trial": "🆓 Prueba Gratis — 3 dias",
        "btn_monthly": "💳 Mensual — 9,99 EUR/mes",
        "btn_semestrial": "💎 6 Meses — 44,99 EUR (-25%)",
        "btn_lifetime": "👑 Lifetime — 79,99 EUR",
        "active_sub": "Tienes una suscripcion activa: *{plan}*\nExpira: {expires}",
        "trial_activated": "✅ *Prueba gratis activada — 3 dias*",
        "join_channel": "Unete al canal premium:",
        "enjoy": "Disfrutalo!",
        "trial_already_used": "Ya has usado tu prueba gratis o tienes una suscripcion.",
        "payment_not_configured": "El pago con tarjeta aun no esta configurado.\nContacta al admin para pagar de otra forma.",
        "pay_now": "💳 Pagar ahora",
        "click_to_pay": "Haz clic para pagar con tarjeta:",
        "payment_error": "Error al crear el pago. Intentalo mas tarde.",
        "pay_card": "Tarjeta de credito",
        "pay_stars": "Telegram Stars",
        "choose_payment": "Elige tu metodo de pago:",
        "stars_invoice_desc": "Suscripcion ScoreRadar — {plan}",
        "payment_received": "✅ *Pago recibido — {plan}*",
        "lifetime_thanks": "Acceso de por vida. Gracias!",
        "expires_on": "Expira el: {date}",
        "sub_expired": "⏰ Tu suscripcion ha expirado.\nEscribe /start para reabonarte.",
        "alerts_off": "🔴 Alertas desactivadas.\nEscribe /start para reactivar.",
        "loading_matches": "🔄 Cargando partidos en vivo...",
        "no_live_matches": "❌ No hay partidos en vivo actualmente.",
        "live_title": "⚽ *PARTIDOS EN VIVO*",
        "matches_count": "📊 {count} partidos en curso",
        "leagues_title": "🏆 *LIGAS*\n\nHaz clic para activar/desactivar:",
        "select_all": "🔄 Seleccionar todo",
        "deselect_all": "🚫 Deseleccionar todo",
        "sensitivity_title": "🔒 *SENSIBILIDAD*",
        "sensitivity_current": "Umbral actual: *{value}/100*",
        "sensitivity_usage": (
            "Uso: `/sensitivity 50`\n"
            "• 40-50 = muy sensible (muchas alertas)\n"
            "• 60-70 = equilibrado (recomendado)\n"
            "• 80-90 = estricto (pocas alertas, alta confianza)"
        ),
        "sensitivity_updated": "✅ Umbral de confianza actualizado: *{value}/100*",
        "sensitivity_invalid": "❌ Valor invalido. Usa un numero entre 10 y 95.",
        "status_title": "📋 *STATUS*",
        "status_active": "🟢 Activo",
        "status_inactive": "🔴 Inactivo",
        "status_threshold": "🔒 Umbral: {value}/100",
        "status_leagues": "🏆 Ligas ({count}):",
        "status_more": "  ... y {count} mas",
        "status_scan": "⏱ Escaneo cada {interval}s",
        "expires_never": "Nunca",
        "lang_set": "🇪🇸 Idioma configurado en *Espanol*",
        "lang_title": "🌍 *IDIOMA / LANGUAGE*\n\nElige tu idioma:",
        "referral_info": (
            "🤝 *REFERIDOS*\n\n"
            "Tu enlace: `{link}`\n\n"
            "👥 Referidos de pago: *{count}*\n"
            "🎯 Siguiente nivel: *{next_tier}* → {next_reward}\n\n"
            "📊 *Niveles:*\n"
            "• 3 referidos → 1 mes gratis\n"
            "• 5 referidos → 3 meses gratis\n"
            "• 10 referidos → 6 meses gratis\n"
            "• 20 referidos → acceso de por vida"
        ),
        "referral_reward": "🎉 *Felicidades!* Alcanzaste *{count} referidos*!\nRecompensa: *{reward}*",
        "referral_all_unlocked": "Todos los niveles desbloqueados!",
        # --- Alertas ---
        "alert_title": "⚽ SENAL DE GOL DETECTADA",
        "alert_live": "🟢 En vivo · {elapsed}' · Marcador: {home_goals} – {away_goals}",
        "alert_analysis": "📊 ANALISIS EN VIVO",
        "alert_minute": "⏱ Minuto",
        "alert_score": "📈 Marcador",
        "alert_shots": "🎯 Tiros a puerta",
        "alert_xg": "📉 xG",
        "alert_corners": "🔄 Corners",
        "alert_prematch": "📈 Pre-partido",
        "alert_context": "🧠 CONTEXTO DEL PARTIDO",
        "alert_signal": "🎯 SENAL DE TRADING",
        "alert_entry": "📍 Punto de entrada",
        "alert_odds": "💰 Cuota objetivo",
        "alert_window": "⏳ Ventana de gol",
        "alert_probs": "📈 Probabilidades",
        "alert_before_70": "├ Antes del min 70",
        "alert_full_match": "└ Hasta el final",
        "alert_optimal": "💎 Apuesta optima",
        "alert_next_goal": "→ Proximo gol",
        "alert_aggressive": "⚡ Apuesta agresiva",
        "alert_before_end": "→ Gol antes del final MT{half}",
        "alert_confidence": "🔒 Puntuacion de confianza",
        "ctx_xg_debt": "El xG ({debt} por encima del marcador) indica que las ocasiones estan ahi pero el marcador no lo refleja.",
        "ctx_dominates": "{team} domina con {possession} de posesion.",
        "ctx_saves": "Los porteros estan bajo presion ({saves} paradas combinadas).",
        "ctx_shots": "Alta intensidad ofensiva ({shots} tiros a puerta).",
        "ctx_no_goal": "Partido sin goles, la presion aumenta.",
        "ctx_tight_score": "Marcador ajustado al final del partido, ambos equipos empujan.",
        "ctx_peak": "Franja {start}'-{end}' = pico historico de goles.",
    },
    "pt": {
        "start_title": "⚽ *SCORERADAR*",
        "start_separator": "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "start_desc": (
            "Receba sinais Over ao vivo com uma alta taxa de sucesso.\n"
            "Acesso ao canal premium com todos os alertas em tempo real."
        ),
        "plan_trial": "🆓 *Teste Gratis* — 3 dias de acesso completo",
        "plan_monthly": "💳 *Mensal* — 9,99 EUR/mes",
        "plan_semestrial": "💎 *6 Meses* — 44,99 EUR (7,50 EUR/mes)",
        "plan_lifetime": "👑 *Lifetime* — 79,99 EUR, acesso vitalicio",
        "choose_plan": "Escolha seu plano:",
        "referral_short": "Indique amigos e ganhe acesso gratis",
        "lang_short": "Mudar idioma",
        "btn_trial": "🆓 Teste Gratis — 3 dias",
        "btn_monthly": "💳 Mensal — 9,99 EUR/mes",
        "btn_semestrial": "💎 6 Meses — 44,99 EUR (-25%)",
        "btn_lifetime": "👑 Lifetime — 79,99 EUR",
        "active_sub": "Voce tem uma assinatura ativa: *{plan}*\nExpira: {expires}",
        "trial_activated": "✅ *Teste gratis ativado — 3 dias*",
        "join_channel": "Entre no canal premium:",
        "enjoy": "Aproveite!",
        "trial_already_used": "Voce ja usou seu teste gratis ou tem uma assinatura.",
        "payment_not_configured": "O pagamento com cartao ainda nao esta configurado.\nEntre em contato com o admin para pagar de outra forma.",
        "pay_now": "💳 Pagar agora",
        "click_to_pay": "Clique para pagar com cartao:",
        "payment_error": "Erro ao criar o pagamento. Tente novamente mais tarde.",
        "pay_card": "Cartao de credito",
        "pay_stars": "Telegram Stars",
        "choose_payment": "Escolha seu metodo de pagamento:",
        "stars_invoice_desc": "Assinatura ScoreRadar — {plan}",
        "payment_received": "✅ *Pagamento recebido — {plan}*",
        "lifetime_thanks": "Acesso vitalicio. Obrigado!",
        "expires_on": "Expira em: {date}",
        "sub_expired": "⏰ Sua assinatura expirou.\nDigite /start para assinar novamente.",
        "alerts_off": "🔴 Alertas desativados.\nDigite /start para reativar.",
        "loading_matches": "🔄 Carregando jogos ao vivo...",
        "no_live_matches": "❌ Nenhum jogo ao vivo no momento.",
        "live_title": "⚽ *JOGOS AO VIVO*",
        "matches_count": "📊 {count} jogos em andamento",
        "leagues_title": "🏆 *LIGAS*\n\nClique para ativar/desativar:",
        "select_all": "🔄 Selecionar tudo",
        "deselect_all": "🚫 Desmarcar tudo",
        "sensitivity_title": "🔒 *SENSIBILIDADE*",
        "sensitivity_current": "Limite atual: *{value}/100*",
        "sensitivity_usage": (
            "Uso: `/sensitivity 50`\n"
            "• 40-50 = muito sensivel (muitos alertas)\n"
            "• 60-70 = equilibrado (recomendado)\n"
            "• 80-90 = rigoroso (poucos alertas, alta confianca)"
        ),
        "sensitivity_updated": "✅ Limite de confianca atualizado: *{value}/100*",
        "sensitivity_invalid": "❌ Valor invalido. Use um numero entre 10 e 95.",
        "status_title": "📋 *STATUS*",
        "status_active": "🟢 Ativo",
        "status_inactive": "🔴 Inativo",
        "status_threshold": "🔒 Limite: {value}/100",
        "status_leagues": "🏆 Ligas ({count}):",
        "status_more": "  ... e mais {count}",
        "status_scan": "⏱ Verificacao a cada {interval}s",
        "expires_never": "Nunca",
        "lang_set": "🇵🇹 Idioma definido como *Portugues*",
        "lang_title": "🌍 *IDIOMA / LANGUAGE*\n\nEscolha seu idioma:",
        "referral_info": (
            "🤝 *INDICACAO*\n\n"
            "Seu link: `{link}`\n\n"
            "👥 Indicados pagantes: *{count}*\n"
            "🎯 Proximo nivel: *{next_tier}* → {next_reward}\n\n"
            "📊 *Niveis:*\n"
            "• 3 indicados → 1 mes gratis\n"
            "• 5 indicados → 3 meses gratis\n"
            "• 10 indicados → 6 meses gratis\n"
            "• 20 indicados → acesso vitalicio"
        ),
        "referral_reward": "🎉 *Parabens!* Voce alcancou *{count} indicados*!\nRecompensa: *{reward}*",
        "referral_all_unlocked": "Todos os niveis desbloqueados!",
        # --- Alertas ---
        "alert_title": "⚽ SINAL DE GOL DETECTADO",
        "alert_live": "🟢 Ao vivo · {elapsed}' · Placar: {home_goals} – {away_goals}",
        "alert_analysis": "📊 ANALISE AO VIVO",
        "alert_minute": "⏱ Minuto",
        "alert_score": "📈 Placar",
        "alert_shots": "🎯 Chutes no gol",
        "alert_xg": "📉 xG",
        "alert_corners": "🔄 Escanteios",
        "alert_prematch": "📈 Pre-jogo",
        "alert_context": "🧠 CONTEXTO DO JOGO",
        "alert_signal": "🎯 SINAL DE TRADING",
        "alert_entry": "📍 Ponto de entrada",
        "alert_odds": "💰 Cota alvo",
        "alert_window": "⏳ Janela de gol",
        "alert_probs": "📈 Probabilidades",
        "alert_before_70": "├ Antes do min 70",
        "alert_full_match": "└ Ate o final",
        "alert_optimal": "💎 Aposta ideal",
        "alert_next_goal": "→ Proximo gol",
        "alert_aggressive": "⚡ Aposta agressiva",
        "alert_before_end": "→ Gol antes do final do {half}T",
        "alert_confidence": "🔒 Pontuacao de confianca",
        "ctx_xg_debt": "O xG ({debt} acima do placar) indica que as chances estao la, mas o placar nao acompanhou.",
        "ctx_dominates": "{team} domina com {possession} de posse.",
        "ctx_saves": "Goleiros sob pressao ({saves} defesas combinadas).",
        "ctx_shots": "Alta intensidade ofensiva ({shots} chutes no gol).",
        "ctx_no_goal": "Jogo sem gols, a pressao esta aumentando.",
        "ctx_tight_score": "Placar apertado no final do jogo, ambos os times empurrando.",
        "ctx_peak": "Faixa {start}'-{end}' = pico historico de gols.",
    },
}

SUPPORTED_LANGS = list(TRANSLATIONS.keys())
DEFAULT_LANG = "fr"

# Mapping Telegram language codes -> our lang codes
TELEGRAM_LANG_MAP = {
    "fr": "fr",
    "en": "en",
    "es": "es",
    "pt": "pt",
    "pt-br": "pt",
}

LANG_FLAGS = {
    "fr": "🇫🇷 Francais",
    "en": "🇬🇧 English",
    "es": "🇪🇸 Espanol",
    "pt": "🇵🇹 Portugues",
}


def get_lang(user_data: dict, telegram_lang: str = None) -> str:
    """Determine la langue de l'utilisateur."""
    # Priorite 1: langue choisie manuellement
    lang = user_data.get("lang")
    if lang and lang in SUPPORTED_LANGS:
        return lang
    # Priorite 2: langue Telegram
    if telegram_lang:
        code = telegram_lang.split("-")[0].lower()
        if code in TELEGRAM_LANG_MAP:
            return TELEGRAM_LANG_MAP[code]
    # Defaut
    return DEFAULT_LANG


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """Recupere une traduction."""
    strings = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
    text = strings.get(key, TRANSLATIONS[DEFAULT_LANG].get(key, key))
    if kwargs:
        text = text.format(**kwargs)
    return text
