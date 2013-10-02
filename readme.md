# XenBackup

Backup script for XenServer

## Features

- support for multiple clusters
- stores backups in simple filesystem tree

## Usage

	usage: xenbackup.py [-h] [--cluster CLUSTER] [--url URL] [--username USERNAME]
	                    [--password PASSWORD] [--repository REPOSITORY]
	                    {list,backup,restore,purge} ...
	
	positional arguments:
	  {list,backup,restore,purge}
	                        commands
	    list                List VMs and Backups
	    backup              Create new Backup(s)
	    restore             Restore a Backup
	    purge               Purge old Backups
	
	optional arguments:
	  -h, --help            show this help message and exit
	  --cluster CLUSTER, -c CLUSTER
	                        Use cluster information from config file
	                        (/etc/xenbackup.json) (default: default)
	  --url URL, -u URL     Xen Server URL (default: https://localhost)
	  --username USERNAME, -l USERNAME
	                        Username (default: root)
	  --password PASSWORD, -p PASSWORD
	                        Password (default: None)
	  --repository REPOSITORY, -r REPOSITORY
	                        Path where the backups are stored (default:
	                        /srv/backup)

### List

Lists all the VMs in the Cluster and the Backups

### Backup

Take a snapshot of a VM and write a backup to the repository

### Restore

Restores a VM from the repository to the cluster

### Purge

Purges old backups, keeping a specified number of most recent ones.