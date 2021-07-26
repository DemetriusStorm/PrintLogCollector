USE [log-print-filials]
GO

/****** Object:  Table [dbo].[Logs]    Script Date: 26.07.2021 13:58:54 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[Logs](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[dtcreated] [varchar](20) NOT NULL,
	[datecreated] [date] NOT NULL,
	[timecreated] [varchar](10) NOT NULL,
	[eventrecordid] [varchar](50) NOT NULL,
	[printserver] [varchar](100) NOT NULL,
	[docname] [varchar](225) NULL,
	[username] [varchar](50) NOT NULL,
	[computer] [varchar](50) NOT NULL,
	[printer] [varchar](50) NOT NULL,
	[count] [int] NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]

GO


