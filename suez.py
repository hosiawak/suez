from datetime import datetime
import math

import click
from rich import box
from rich.console import Console
from rich.table import Table

from lndclient import LndClient


class FeePolicy:
    def __init__(self, base_fee, fee_rate, fee_sigma, time_lock_delta):
        self.base_fee = base_fee
        self.fee_rate = fee_rate
        self.fee_sigma = fee_sigma
        self.time_lock_delta = time_lock_delta

    def calculate(self, channel):
        ratio = channel.local_balance / (channel.local_balance + channel.remote_balance)
        ratio -= 0.5
        coef = math.exp(-self.fee_sigma * ratio * ratio)
        fee_rate = 0.000001 * coef * self.fee_rate
        if fee_rate < 0.000001:
            fee_rate = 0.000001
        base_fee = self.base_fee
        time_lock_delta = self.time_lock_delta
        return base_fee, fee_rate, time_lock_delta


def _sort_channels(c):
    return c.local_balance / (c.local_balance + c.remote_balance)


def _since(ts):
    d = datetime.utcnow() - datetime.utcfromtimestamp(ts)
    return "%0.1f" % (d.total_seconds() / 86400)


@click.command()
@click.option("--base-fee", default=0, help="Set base fee")
@click.option("--fee-rate", default=0, help="Set fee rate")
@click.option("--fee-sigma", default=24, help="Fee sigma")
@click.option("--time-lock-delta", default=40, help="Set time lock delta")
def suez(base_fee, fee_rate, fee_sigma, time_lock_delta):
    ln = LndClient()

    if base_fee and fee_rate:
        policy = FeePolicy(base_fee, fee_rate, fee_sigma, time_lock_delta)
        ln.apply_fee_policy(policy)
        ln.refresh()

    table = Table(box=box.SIMPLE)
    table.add_column("\ninbound", justify="right", style="bright_red")
    table.add_column("\nratio", justify="center")
    table.add_column("\noutbound", justify="right", style="green")
    table.add_column("local\nbase_fee\n(msat)", justify="right", style="bright_blue")
    table.add_column("local\nfee_rate\n(ppm)", justify="right", style="bright_blue")
    table.add_column("remote\nbase_fee\n(msat)", justify="right", style="bright_yellow")
    table.add_column("remote\nfee_rate\n(ppm)", justify="right", style="bright_yellow")
    table.add_column("uptime\n\n(%)", justify="right", style="bright_black")
    table.add_column("last\nforward\n(days)", justify="right")
    table.add_column("earned\nfees\n(sat)", justify="right", style="bright_cyan")
    table.add_column("\nalias")

    total_local, total_remote, total_fees = 0, 0, 0

    for c in sorted(ln.channels.values(), key=_sort_channels):
        send = int(10 * c.local_balance / (c.local_balance + c.remote_balance))
        recv = 10 - send
        bar = (
            "[bright_red]"
            + ("·" * recv)
            + "[/bright_red]"
            + "|"
            + "[green]"
            + ("·" * send)
            + "[/green]"
        )
        uptime = 100 * c.uptime // c.lifetime
        total_fees += c.earned_fees
        total_local += c.local_balance
        total_remote += c.remote_balance
        table.add_row(
            "{:,}".format(c.remote_balance),
            bar,
            "{:,}".format(c.local_balance),
            str(c.local_base_fee),
            str(c.local_fee_rate),
            str(c.remote_base_fee),
            str(c.remote_fee_rate),
            str(uptime),
            _since(c.last_forward) if c.last_forward else "never",
            "{:,}".format(c.earned_fees) if c.earned_fees else "-",
            c.remote_alias,
        )

    table.add_row("─" * 11, None, "─" * 11, None, None, None, None, None, None, "─" * 7)
    table.add_row(
        "{:,}".format(total_remote),
        None,
        "{:,}".format(total_local),
        None,
        None,
        None,
        None,
        None,
        None,
        "{:,}".format(total_fees),
    )

    console = Console()
    console.print(table)