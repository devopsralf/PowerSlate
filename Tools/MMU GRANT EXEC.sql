USE [Campus6_odyssey]

--GRANT EXEC ON [custom].[PS_selISIR] TO [MERCY\powerslate_svc]
GRANT EXEC ON [custom].[PS_updDemographics] TO [MERCY\powerslate_svc]
GRANT EXEC ON [custom].[PS_updAcademicAppInfo] TO [MERCY\powerslate_svc]
--GRANT EXEC ON [custom].[PS_updAction] to [MERCY\powerslate_svc]
GRANT EXEC ON [custom].[PS_selProfile] to [MERCY\powerslate_svc]
GRANT EXEC ON [custom].[PS_selRAStatus] to [MERCY\powerslate_svc]
--GRANT EXEC ON [custom].[PS_updSMSOptIn] to [MERCY\powerslate_svc]
--GRANT EXEC ON [custom].[PS_selPFChecklist] to [MERCY\powerslate_svc]
GRANT EXEC ON [custom].[PS_insNote] to [MERCY\powerslate_svc]
GRANT EXEC ON [custom].[PS_updUserDefined] to [MERCY\powerslate_svc]
GRANT SELECT, UPDATE, VIEW DEFINITION ON [USERDEFINEDIND]  to [MERCY\powerslate_svc]
