#!/usr/bin/python
import curses
import threading
import time

from docker import Client
#from urllib2 import TimeoutException
class TimeoutException(Exception): pass

window = None
cli = None
size = None
cpu_old = None
container_threads = {}
containers = []
DOCKER_CONTAINERS = " DOCKER MONITOR "
high_ind = 0


class ContainerThreadClass(threading.Thread):
	''' Container Thread Class '''
	def __init__(self, container_id):
		super(ContainerThreadClass, self).__init__()
		self._stopper = threading.Event()
		self._container_id = container_id
		self._stats_stream = cli.stats(container_id, decode=True)
		self._stats = {}
	def run(self):
		for i in self._stats_stream:
			self._stats = i
			time.sleep(0.1)
			if self._stopper.isSet():
				break
	def stop(self):
		self._stopper.set()

def init_scr():
	''' Initialise Global Variables'''
	global window, size
	window = curses.initscr()
	window.keypad(0)
	window.nodelay(1)
	size = window.getmaxyx()
	curses.start_color()
	curses.curs_set(0)
	curses.cbreak()
	curses.noecho()  #hide user input

def init_conn():
	global cli
	cli = Client(base_url="unix://var/run/docker.sock")

def create(img, cmd):
	'''Create container'''
	container = cli.create_container(image=img, command=cmd, tty=True) #A dictionary with an image 'Id' key and a 'Warnings' key.
	cli.start(container)
	return container 

def stop(container):
	'''Stop Container'''
	try:
		cli.kill(container)
	except APIError:
		cli.wait(container)

	try:
		cli.stop(container)
	except APIError:
		pass
	
def stop_threads():
	'''Stop Threads'''
	for cont in container_threads.values():	
		cont.stop()

def clean():
	curses.nocbreak()
	window.keypad(0)
	curses.echo()
	curses.endwin()

def print_header():
	'''Headings'''
	window.addstr(0, size[1]/2-len(DOCKER_CONTAINERS)/2, DOCKER_CONTAINERS, curses.A_BOLD)
	curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
	window.addstr(1, 1, "Id", curses.color_pair(1))
	window.addstr(1, 16, "Name", curses.color_pair(1))
	window.addstr(1, 40, "Image", curses.color_pair(1))
	window.addstr(1, 60, "Status", curses.color_pair(1))
	window.addstr(1, 80, "IP", curses.color_pair(1))
	window.addstr(1, 100, "CPU%", curses.color_pair(1))

def print_footer():
	'''Navigate Options'''
	downmargin = size[0]-2
	rightmargin = size[1]/4
	window.addstr(downmargin, rightmargin, "c:Create Container", curses.color_pair(1))
	window.addstr(downmargin, rightmargin+20, "s:Stop Container", curses.color_pair(1))
	window.addstr(downmargin, rightmargin+38, "j:Navigate Up", curses.color_pair(1)) 
	window.addstr(downmargin, rightmargin+54, "k:Navigate Down", curses.color_pair(1)) 
	window.addstr(downmargin, rightmargin+71, "q:Quit", curses.color_pair(1)) 

def main():
	while True:
		window.erase() #clear the window
		window.border() #Draw a border around the edges of the window. 
		print_header()
		print_footer()
		margin = 3

		global containers, container
		old_containers = set([c[u'Id'] for c in containers])
		containers = cli.containers()
		dead_containers = old_containers - set([c[u'Id'] for c in containers])
		for cont in dead_containers:
			container_threads[cont].stop()
			del container_threads[cont]

		
		ch = window.getch()
		global high_ind
		if ch == ord('k') and high_ind <len(containers)-1:
			high_ind += 1
		elif ch == ord('j') and high_ind > 0:
			high_ind -= 1
		elif ch == ord('q'):
			break
		elif ch == ord('c'):
			global container 
			container = create('busybox','')
		elif ch == ord('s') and len(containers) is not 0:
			stop(containers[high_ind])
			
		if len(containers):
			for i in range(0,len(containers)):
				if i == high_ind:	
					window.addstr(margin, 1, " "*100, curses.A_STANDOUT)
					window.addstr(margin, 1, containers[i][u'Id'][:8], curses.A_STANDOUT)
					window.addstr(margin, 16, containers[i][u'Names'][0], curses.A_STANDOUT)
					window.addstr(margin, 40, containers[i][u'Image'], curses.A_STANDOUT)
					window.addstr(margin, 60, containers[i][u'Status'], curses.A_STANDOUT)
					container_info = cli.inspect_container(containers[i][u'Id'])
					window.addstr(margin, 80, container_info[u'NetworkSettings'][u'IPAddress'], curses.A_STANDOUT)

				else:
					window.addstr(margin, 1, containers[i][u'Id'][:8])
					window.addstr(margin, 16, containers[i][u'Names'][0])
					window.addstr(margin, 40, containers[i][u'Image'])
					window.addstr(margin, 60, containers[i][u'Status'])
					container_info = cli.inspect_container(containers[i][u'Id'])
					window.addstr(margin, 80, container_info[u'NetworkSettings'][u'IPAddress'])


				window.addstr(margin, 100, "[")
				if containers[i][u'Id'] not in container_threads:
					t = ContainerThreadClass(containers[i][u'Id'])
					container_threads[containers[i][u'Id']] = t
					t.start()
				try:
					stats = container_threads[containers[i][u'Id']]._stats
					cpu_new = {}
					cpu_new['total_usage'] = stats['cpu_stats']['cpu_usage']['total_usage']
					cpu_new['system_cpu_usage'] = stats['cpu_stats']['system_cpu_usage']
				except KeyError as e:
					pass
				else:
					global cpu_old
					if cpu_old is None:
						cpu_old = {}
						cpu_old[containers[i][u'Id']] = cpu_new
					if containers[i][u'Id'] not in cpu_old:
						cpu_old[containers[i][u'Id']] = cpu_new
					else:
						cpu_delta = float(cpu_new['total_usage'] - cpu_old[containers[i][u'Id']]['total_usage'])
						system_delta = float(cpu_new['system_cpu_usage'] - cpu_old[containers[i][u'Id']]['system_cpu_usage'])
						if system_delta > 0.0:
							total = (cpu_delta / system_delta) * 100
							for i in range(int(total/5)):
								window.addstr(margin, 101+i, "|")
							window.addstr(margin, 122, str(round(total, 2)) + "%")
						cpu_old[containers[i][u'Id']] = cpu_new
				window.addstr(margin, 121, "]")
				margin = margin + 1
		else:
			window.addstr(margin, 1, "No running containers")
		
	
		window.refresh()
		curses.napms(1000)


if __name__ == "__main__":
	init_scr()
	init_conn()
	main()
	stop_threads()
	clean()

		