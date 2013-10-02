#!/usr/bin/env python

import os
import sys
import re
import ago
import time
import json
import argparse
import logging
import requests
import XenAPI
import calendar
from datetime import datetime

log = logging.getLogger("xenBackup")
log.addHandler(logging.StreamHandler())
log.setLevel(logging.DEBUG)


## backup names
def generate_name(uuid):
	return 'backup_' + uuid + '_' + time.strftime("%Y%m%d-%H%M", time.gmtime())


def parse_name(name):
	keyword, uuid, date = name.replace('.xva', '').split('_')
	if keyword != 'backup':
		raise Exception("Not a backup file: " + name)
	date = datetime.fromtimestamp(calendar.timegm(time.strptime(date, "%Y%m%d-%H%M")))
	return (uuid, date)


## xen api functions
def create_session(url, username, password):
	try:
		session = XenAPI.Session(url)
		session.xenapi.login_with_password(username, password)
	except Exception, e:
		log.error("XenAPI Login error: %s", e)
		sys.exit(-1)
	return session


def create_snapshot(session, ref, name):
	snapshot = session.xenapi.VM.snapshot(ref, name)
	session.xenapi.VM.set_is_a_template(snapshot, False)
	return snapshot


def download(url, file):
	chunk_size = 1024 * 1024 * 4 # 4 Megs
	req = requests.get(url, stream = True, verify = False)	
	with open(file, 'wb') as f:
		for chunk in req.iter_content(chunk_size = chunk_size):
			if not chunk: # filter out keep-alive new chunks
				continue
			f.write(chunk)
			f.flush()


## helper functions 
def generate_inventory(vms, repository):
	inv = {}

	for ref, vm in vms.items():
		if vm["is_a_template"] or vm['is_a_snapshot'] or vm["is_control_domain"] or vm["power_state"] != "Running":
			continue
		inv[vm["uuid"]] = vm
		inv[vm["uuid"]]["_ref"]     = ref	
		inv[vm["uuid"]]["_backups"] = []
	for vm in os.listdir(repository):
		if vm not in inv:
			inv[vm] = {'_backups': []}
		for backup in sorted(os.listdir(repository + '/' + vm)):
			try:
				uuid, date = parse_name(backup)
			except:
				continue
			inv[vm]['_backups'] += [(backup, uuid, date)]
	return inv


def find_backup(uuid_or_file, repository, inventory):
	if uuid_or_file.endswith('.xva'):
		# file
		if os.path.isfile(uuid_or_file):
			# absolute file+path name
			return uuid_or_file
		else:
			# try find it in repository
			try:
				uuid, date = parse_name(uuid_or_file)
			except:
				return None
			file = repository + '/' + uuid + '/' + uuid_or_file
			if not os.path.isfile(file):
				return None
			return file

	else:
		# uuid
		if uuid_or_file not in inventory:
			return None
		if len(inventory[uuid_or_file]['_backups'])	< 1:
			return None
		return repository + '/' + uuid_or_file + '/' + inventory[uuid_or_file]['_backups'][0][0]

		
		
def print_vm_backups(uuid, vm):
	print 'VM: ' + uuid
	print '\tState: ' + vm.get('power_state', 'Only Backup')
	print '\tBackups:'
	if not vm['_backups']:
		print '\t\t-none-'
	for backup in vm['_backups']:
		print '\t\t' + backup[0] + '\t' + ago.human(backup[2])


## commands	
def list(args):
	session = create_session(args.url, args.username, args.password)
	vms = session.xenapi.VM.get_all_records()
	
	inventory = generate_inventory(vms, args.repository)

	if args.uuid:
		try:
			print_vm_backups(args.uuid, inventory[args.uuid])
		except:
			print 'VM with UUID "' + args.uuid + '" not found.'
	else:
		for uuid, vm in sorted(inventory.items()):
			print_vm_backups(uuid, vm)
			

def backup(args):
	session = create_session(args.url, args.username, args.password)
	vms = args.uuid
	if not args.uuid:
		vms = [] # todo: get all running vms

	for vm in vms:
		snapshot = None
		log.info("Backup for %s started", vm)
		try:
			ref  = session.xenapi.VM.get_by_uuid(vm)
			name = generate_name(vm)		
			path = "%s/%s" % (args.repository, vm)
			file = "%s/%s.xva" % (path, name)

			snapshot = create_snapshot(session, ref, name)
			log.debug("Snapshot for %s finished, starting download", vm)

			if not os.path.exists(path):
				os.makedirs(path)
				
			url  = "%s/export?ref=%s&session_id=%s" % (args.url, snapshot, session.handle)
			download(url, file)

			log.info("Backup for %s finished", vm)			
		except Exception, e:
			log.error("Backup for %s failed: %s", vm, e)
			# try to clean up a potentially incomplete backup
			try:
				os.unlink(file)
			except:
				pass
		finally:
			if snapshot:
				session.xenapi.VM.destroy(snapshot)


def restore(args):
	session = create_session(args.url, args.username, args.password)
	vms = session.xenapi.VM.get_all_records()
	inventory = generate_inventory(vms, args.repository)
	file = find_backup(args.uuid_or_file, args.repository, inventory)
	if not file:
		print 'Could not find backup'
		return
	
	log.debug("Importing %s", file)
	
	# upload
	task_id = session.xenapi.task.create('VM.import', 'Restore of ' + file)	
	url  = "%s/import?session_id=%s&task_id=%s" % (args.url, session.handle, task_id)
	with open(file) as f:
		try:
			response = requests.put(url, data=f, verify=False, stream=True)
			response.raise_for_status()
		except Exception, e:
			log.error("Restore failed: %s", e)
			return

	log.debug("Upload of %s done, waiting for import to finish", file)
	while True:
		task_record = session.xenapi.task.get_record(task_id)
		if task_record['status'] != 'pending':
			break
		time.sleep(1)
		
	if task_record['status'] != 'success':
		log.error("Restore failed: %s", task_record.get('error_info', 'Unknown Error'))
		return

	# get the uuid
	ref = re.findall('(OpaqueRef:[0-9a-f-]+)', task_record['result'])[0]
	log.info("Restored: %s", session.xenapi.VM.get_record(ref)['uuid'])


def purge(args):
	session = create_session(args.url, args.username, args.password)
	vms = session.xenapi.VM.get_all_records()
	inventory = generate_inventory(vms, args.repository)
	
	for uuid, vm in sorted(inventory.items()):
		for backup in vm['_backups'][:-args.n]:
			log.info("Purging %s", backup[0])
			os.unlink(args.repository + '/' + uuid + '/' + backup[0])
	
	
def read_config():
	try:
		config = json.load(open('/etc/xenbackup.json'))
	except Exception, e:
		print e
		config = {}
	return config

def parse_args():
	cluster_parser = argparse.ArgumentParser(add_help=False)
	cluster_parser.add_argument('--cluster', '-c', help='Use cluster information from config file (/etc/xenbackup.json)', default='default')
	args, remaining_argv = cluster_parser.parse_known_args()	
	
	
	config = read_config()


	if args.cluster != 'default' and args.cluster not in config:
		log.error("Cluster not defined in configuration File")
		sys.exit(-1)

	defaults = {
		'url':        'https://localhost',
		'username':   'root',
		'repository': '/srv/backup'
	}
	
	defaults.update(config.get(args.cluster, {}))
	
	parser = argparse.ArgumentParser(
		parents         = [cluster_parser],
		formatter_class = argparse.ArgumentDefaultsHelpFormatter
	)
	parser.set_defaults(**defaults)
	
	parser.add_argument('--url',        '-u', help='Xen Server URL')
	parser.add_argument('--username',   '-l', help='Username')
	parser.add_argument('--password',   '-p', help='Password')
	parser.add_argument('--repository', '-r', help='Path where the backups are stored')

	subparsers = parser.add_subparsers(help='commands')
	
	# list
	list_parser = subparsers.add_parser('list', help='List VMs and Backups')
	list_parser.add_argument('uuid', help='VM UUID', nargs='?')
	list_parser.set_defaults(func=list)
	
	# create backup
	backup_parser = subparsers.add_parser('backup', help='Create new Backup(s)')
	backup_parser.add_argument('uuid', help='VM UUID(s)', nargs='*')
	backup_parser.set_defaults(func=backup)
	
	# restore
	restore_parser = subparsers.add_parser('restore', help='Restore a Backup')
	restore_parser.add_argument('uuid_or_file', metavar='uuid|file', help='VM UUID (restores the latest backup) or filename')
	restore_parser.set_defaults(func=restore)
	
	# purge
	purge_parser = subparsers.add_parser('purge', help='Purge old Backups')
	purge_parser.add_argument('n', type=int, help='Number of Backups to keep')	
	purge_parser.set_defaults(func=purge)
	
	return parser.parse_args(remaining_argv)


def main():
	args = parse_args()
	args.func(args)	

	
if __name__ == '__main__':
	main()
