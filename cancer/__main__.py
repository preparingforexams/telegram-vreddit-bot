import click

from cancer import command


@click.group()
def app():
    pass


@app.command("handle_updates")
def handle_updates():
    command.handle_updates.run()


if __name__ == '__main__':
    app.main()
