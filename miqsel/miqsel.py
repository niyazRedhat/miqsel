import os
import time

import click
import docker
import yaml


class Connection(object):
    def __init__(self):
        self.client = None
        self.container = None
        self.conf = None


connection = click.make_pass_decorator(Connection, ensure=True)


@click.group()
@connection
def cli(connection):
    """"Entry Point for miqsel commandline"""

    try:
        connection.client = docker.from_env()
    except Exception:
        click.echo("Fail to connect docker")
        exit(1)

    # Initial check for project path else set it.
    conf = Configuration()
    data = Configuration().read()

    if data["container"]["project_dir"] == "":
        click.echo("set project path like > /home/user_name/../../integration_tests")
        data["container"]["project_dir"] = click.prompt("Project path")
        conf.write(data)
    connection.conf = data


class Configuration(object):
    """Configure miqsel"""

    def __init__(self, conf_file="conf.yaml"):
        self.conf_file = conf_file

    def read(self):
        try:
            with open(self.conf_file, "r") as ymlfile:
                return yaml.load(ymlfile)
        except IOError:
            return {}

    def write(self, cfg):
        with open(self.conf_file, "w") as ymlfile:
            return yaml.safe_dump(cfg, ymlfile, default_flow_style=False)


def set_env(hostname=None, browser=None):
    """"Modify env.local.yaml file of integration test project"""
    data = Configuration().read()
    server_data = data["container"]
    env_data = data["env"]
    port = server_data.get("server_port")
    path = os.path.join(server_data.get("project_dir"), "conf/env.local.yaml")

    env = Configuration(path)
    local_env = env.read()
    env_data = local_env if local_env else env_data

    if hostname:
        url = "http://{host}:{port}/wd/hub".format(host=hostname, port=port)
        env_data["browser"]["webdriver_options"]["command_executor"] = url

    if browser:
        env_data["browser"]["webdriver_options"]["desired_capabilities"]["browserName"] = browser
    env.write(env_data)


@cli.command(help="Configure Miq Selenium webdriver")
def config():
    """Configure selenium attributes"""
    conf = Configuration()
    data = conf.read()
    cfg = data["container"]
    cfg["project_dir"] = click.prompt("Miq project working dir", default=cfg.get("project_dir"))
    cfg["container_name"] = click.prompt("Container name", default=cfg.get("name"))
    cfg["image"] = click.prompt("Docker selenium driver image", default=cfg.get("image"))
    cfg["vnc_port"] = click.prompt("VNC running on port?", default=cfg.get("vnc_port"))
    cfg["server_port"] = click.prompt(
        "Selenium server running on port?", default=cfg["server_port"]
    )
    conf.write(cfg=data)
    click.echo("Configuration saved successfully...")


@connection
def get_container(connection):
    """get container object"""
    try:
        return connection.client.containers.get(connection.conf["container"]["name"])
    except docker.errors.NotFound:
        return None


@cli.command(help="Miq Selenium Server Hostname")
def hostname():
    """Get miq selenium container hostname"""
    container = get_container()
    host = container.attrs["NetworkSettings"]["IPAddress"] if container else None
    click.echo(host)
    return host


@cli.command(help="VNC viewer")
@click.option("-u", "--url", default=None, help="Server url with port <hostname:port>")
def viewer(url):
    """Trigger tiger vnc"""
    os.system("vncviewer {url}&".format(url=url))


@cli.command(help="Start Miq Selenium Server")
@connection
@click.pass_context
def start(ctx, connection):
    """Pull image and start miq selenium container with yaml modification"""
    container = get_container()
    img = connection.conf["container"]["image"]
    name = connection.conf["container"]["name"]
    vnc_port = connection.conf["container"]["vnc_port"]

    if not container:
        connection.client.containers.run(img, name=name, detach=True, auto_remove=True)
        click.echo("{} container started".format(name))
        time.sleep(10)

        t0 = time.time()
        while True:
            host = ctx.invoke(hostname)
            if host:
                url = "{hostname}:{port}".format(hostname=host, port=vnc_port)
                break
            elif time.time() > (t0 + 20):
                click.echo("Timeout: Fail to get hostname. Check for selenium server status")
                exit(0)

        set_env(hostname=host)
        ctx.invoke(viewer, url=url)

    elif getattr(container, "status", None) == "exited":
        container.start()
        click.echo("{} container started".format(name))
    else:
        click.echo("Container in {} state".format(container.status))


@cli.command(help="Stop Miq Selenium Server")
def stop():
    """stop miq selenium server"""
    container = get_container()

    if getattr(container, "status", None) == "running":
        container.stop()
    else:
        click.echo("Nothing to stop")


@cli.command(help="Status of Miq Selenium Server")
def status():
    """check status of miq selenium container"""
    container = get_container()
    if container:
        click.echo(container.status)
    else:
        click.echo("Not running...")


@cli.command(help="Set Browser")
@click.option("-c", "--chrome", "browser", flag_value="chrome", default=True, help="Chrome")
@click.option("-f", "--firefox", "browser", flag_value="firefox", help="Firefox")
def browser(browser):
    """choose browser"""
    set_env(browser=browser)
