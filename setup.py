#!/usr/bin/env python

from distutils.core import setup

setup(
	name             = 'XenBackup',
	version          = '0.1',
	description      = 'Backup script for XenServer',
	author           = 'Sebastian Wiedenroth',
	author_email     = 'sw@core.io',
	url              = 'https://github.com/wiedi/xenbackup',
	scripts          = ['xenbackup', ],
	install_requires = [
		"XenAPI   == 1.2",
		"requests == 2.0.0",
		"ago      == 0.0.5",
	],
)
