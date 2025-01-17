USE [Campus6]

SELECT PROGRAM
	,DEGREE
	,CURRICULUM
	,count(*) [Count]
	,(PROGRAM + '/' + DEGREE + '/' + CURRICULUM) AS [Export]
FROM ACADEMIC
WHERE ACADEMIC_YEAR >= 2019
	AND ACADEMIC_FLAG = 'y'
GROUP BY PROGRAM
	,DEGREE
	,CURRICULUM
ORDER BY CURRICULUM
	,count(*) DESC
