USE [Campus6]

:setvar service_user "PowerSlate"

GRANT EXEC ON [custom].[PS_selISIR] TO $(service_user)
GRANT EXEC ON [custom].[PS_updDemographics] TO $(service_user)
GRANT EXEC ON [custom].[PS_updAcademicAppInfo] TO $(service_user)
GRANT EXEC ON [custom].[PS_updAcademicKey] TO $(service_user)
GRANT EXEC ON [custom].[PS_updAction] to $(service_user)
GRANT EXEC ON [custom].[PS_selProfile] to $(service_user)
GRANT EXEC ON [custom].[PS_selRAStatus] to $(service_user)
GRANT EXEC ON [custom].[PS_updSMSOptIn] to $(service_user)
GRANT EXEC ON [custom].[PS_selPFChecklist] to $(service_user)
GRANT EXEC ON [custom].[PS_insNote] to $(service_user)
GRANT EXEC ON [custom].[PS_updUserDefined] to $(service_user)
GRANT EXEC ON [custom].[PS_updEducation] to $(service_user)
GRANT EXEC ON [custom].[PS_updTestscore] to $(service_user)
GRANT EXEC ON [custom].[PS_updProgramOfStudy] to $(service_user)
GRANT EXEC ON [custom].[PS_selActions] to $(service_user)
GRANT EXEC ON [custom].[PS_delAction] to $(service_user)
GRANT EXEC ON [custom].[PS_selActionDefinition] to $(service_user)
GRANT SELECT, UPDATE, VIEW DEFINITION ON [USERDEFINEDIND]  to $(service_user)
GRANT EXEC ON [custom].[PS_selPersonDuplicate] to $(service_user)
GRANT EXEC ON [custom].[PS_updApplicationFormSetting] to $(service_user)
GRANT EXEC ON [custom].[PS_updStop] to $(service_user)
GRANT EXEC ON [custom].[PS_selPFAwardsXML] to $(service_user)
GRANT EXEC ON [custom].[PS_selAcademicCalendar] to $(service_user)

USE [PowerCampusMapper]
GRANT INSERT ON PowerSlate_AppStatus_Log TO $(service_user)
