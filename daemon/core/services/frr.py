"""
frr.py: defines routing services provided by FRRouting.
Assumes installation of FRR via https://deb.frrouting.org/
"""

from core import constants
from core.emulator.enumerations import LinkTypes
from core.nodes import ipaddress
from core.nodes.network import PtpNet
from core.nodes.physical import Rj45Node
from core.services.coreservices import CoreService


class FRRZebra(CoreService):
    name = "FRRzebra"
    group = "FRR"
    dirs = ("/usr/local/etc/frr", "/var/run/frr", "/var/log/frr")
    configs = (
        "/usr/local/etc/frr/frr.conf",
        "frrboot.sh",
        "/usr/local/etc/frr/vtysh.conf",
        "/usr/local/etc/frr/daemons",
    )
    startup = ("sh frrboot.sh zebra",)
    shutdown = ("killall zebra",)
    validate = ("pidof zebra",)

    @classmethod
    def generate_config(cls, node, filename):
        """
        Return the frr.conf or frrboot.sh file contents.
        """
        if filename == cls.configs[0]:
            return cls.generateFrrConf(node)
        elif filename == cls.configs[1]:
            return cls.generateFrrBoot(node)
        elif filename == cls.configs[2]:
            return cls.generateVtyshConf(node)
        elif filename == cls.configs[3]:
            return cls.generateFrrDaemons(node)
        else:
            raise ValueError(
                "file name (%s) is not a known configuration: %s", filename, cls.configs
            )

    @classmethod
    def generateVtyshConf(cls, node):
        """
        Returns configuration file text.
        """
        return "service integrated-vtysh-config\n"

    @classmethod
    def generateFrrConf(cls, node):
        """
        Returns configuration file text. Other services that depend on zebra
        will have generatefrrifcconfig() and generatefrrconfig()
        hooks that are invoked here.
        """
        # we could verify here that filename == frr.conf
        cfg = ""
        for ifc in node.netifs():
            cfg += "interface %s\n" % ifc.name
            # include control interfaces in addressing but not routing daemons
            if hasattr(ifc, "control") and ifc.control is True:
                cfg += "  "
                cfg += "\n  ".join(map(cls.addrstr, ifc.addrlist))
                cfg += "\n"
                continue
            cfgv4 = ""
            cfgv6 = ""
            want_ipv4 = False
            want_ipv6 = False
            for s in node.services:
                if cls.name not in s.dependencies:
                    continue
                ifccfg = s.generatefrrifcconfig(node, ifc)
                if s.ipv4_routing:
                    want_ipv4 = True
                if s.ipv6_routing:
                    want_ipv6 = True
                    cfgv6 += ifccfg
                else:
                    cfgv4 += ifccfg

            if want_ipv4:
                ipv4list = filter(
                    lambda x: ipaddress.is_ipv4_address(x.split("/")[0]), ifc.addrlist
                )
                cfg += "  "
                cfg += "\n  ".join(map(cls.addrstr, ipv4list))
                cfg += "\n"
                cfg += cfgv4
            if want_ipv6:
                ipv6list = filter(
                    lambda x: ipaddress.is_ipv6_address(x.split("/")[0]), ifc.addrlist
                )
                cfg += "  "
                cfg += "\n  ".join(map(cls.addrstr, ipv6list))
                cfg += "\n"
                cfg += cfgv6
            cfg += "!\n"

        for s in node.services:
            if cls.name not in s.dependencies:
                continue
            cfg += s.generatefrrconfig(node)
        return cfg

    @staticmethod
    def addrstr(x):
        """
        helper for mapping IP addresses to zebra config statements
        """
        if x.find(".") >= 0:
            return "ip address %s" % x
        elif x.find(":") >= 0:
            return "ipv6 address %s" % x
        else:
            raise ValueError("invalid address: %s", x)

    @classmethod
    def generateFrrBoot(cls, node):
        """
        Generate a shell script used to boot the FRR daemons.
        """
        frr_bin_search = node.session.options.get_config(
            "frr_bin_search", default='"/usr/local/bin /usr/bin /usr/lib/frr"'
        )
        frr_sbin_search = node.session.options.get_config(
            "frr_sbin_search", default='"/usr/local/sbin /usr/sbin /usr/lib/frr"'
        )
        return """\
#!/bin/sh
# auto-generated by zebra service (frr.py)
FRR_CONF=%s
FRR_SBIN_SEARCH=%s
FRR_BIN_SEARCH=%s
FRR_STATE_DIR=%s

searchforprog()
{
    prog=$1
    searchpath=$@
    ret=
    for p in $searchpath; do
        if [ -x $p/$prog ]; then
            ret=$p
            break
        fi
    done
    echo $ret
}

confcheck()
{
    CONF_DIR=`dirname $FRR_CONF`
    # if /etc/frr exists, point /etc/frr/frr.conf -> CONF_DIR
    if [ "$CONF_DIR" != "/etc/frr" ] && [ -d /etc/frr ] && [ ! -e /etc/frr/frr.conf ]; then
        ln -s $CONF_DIR/frr.conf /etc/frr/frr.conf
    fi
    # if /etc/frr exists, point /etc/frr/vtysh.conf -> CONF_DIR
    if [ "$CONF_DIR" != "/etc/frr" ] && [ -d /etc/frr ] && [ ! -e /etc/frr/vtysh.conf ]; then
        ln -s $CONF_DIR/vtysh.conf /etc/frr/vtysh.conf
    fi
}

bootdaemon()
{
    FRR_SBIN_DIR=$(searchforprog $1 $FRR_SBIN_SEARCH)
    if [ "z$FRR_SBIN_DIR" = "z" ]; then
        echo "ERROR: FRR's '$1' daemon not found in search path:"
        echo "  $FRR_SBIN_SEARCH"
        return 1
    fi

    flags=""

    if [ "$1" = "pimd" ] && \\
        grep -E -q '^[[:space:]]*router[[:space:]]+pim6[[:space:]]*$' $FRR_CONF; then
        flags="$flags -6"
    fi

    #force FRR to use CORE generated conf file
    flags="$flags -d -f $FRR_CONF"
    $FRR_SBIN_DIR/$1 $flags

    if [ "$?" != "0" ]; then
        echo "ERROR: FRR's '$1' daemon failed to start!:"
        return 1
    fi
}

bootfrr()
{
    FRR_BIN_DIR=$(searchforprog 'vtysh' $FRR_BIN_SEARCH)
    if [ "z$FRR_BIN_DIR" = "z" ]; then
        echo "ERROR: FRR's 'vtysh' program not found in search path:"
        echo "  $FRR_BIN_SEARCH"
        return 1
    fi

    # fix /var/run/frr permissions
    id -u frr 2>/dev/null >/dev/null
    if [ "$?" = "0" ]; then
        chown frr $FRR_STATE_DIR
    fi

    bootdaemon "zebra"
    for r in rip ripng ospf6 ospf bgp babel; do
        if grep -q "^router \\<${r}\\>" $FRR_CONF; then
            bootdaemon "${r}d"
        fi
    done

    if grep -E -q '^[[:space:]]*router[[:space:]]+pim6?[[:space:]]*$' $FRR_CONF; then
        bootdaemon "pimd"
    fi

    $FRR_BIN_DIR/vtysh -b
}

if [ "$1" != "zebra" ]; then
    echo "WARNING: '$1': all FRR daemons are launched by the 'zebra' service!"
    exit 1
fi
confcheck
bootfrr
""" % (
            cls.configs[0],
            frr_sbin_search,
            frr_bin_search,
            constants.FRR_STATE_DIR,
        )

    @classmethod
    def generateFrrDaemons(cls, node):
        """
        Returns configuration file text.
        """
        return """\
#
# When activation a daemon at the first time, a config file, even if it is
# empty, has to be present *and* be owned by the user and group "frr", else
# the daemon will not be started by /etc/init.d/frr. The permissions should
# be u=rw,g=r,o=.
# When using "vtysh" such a config file is also needed. It should be owned by
# group "frrvty" and set to ug=rw,o= though. Check /etc/pam.d/frr, too.
#
# The watchfrr and zebra daemons are always started.
#
bgpd=yes
ospfd=yes
ospf6d=yes
ripd=yes
ripngd=yes
isisd=yes
pimd=yes
ldpd=yes
nhrpd=yes
eigrpd=yes
babeld=yes
sharpd=yes
pbrd=yes
bfdd=yes
fabricd=yes

#
# If this option is set the /etc/init.d/frr script automatically loads
# the config via "vtysh -b" when the servers are started.
# Check /etc/pam.d/frr if you intend to use "vtysh"!
#
vtysh_enable=yes
zebra_options="  -A 127.0.0.1 -s 90000000"
bgpd_options="   -A 127.0.0.1"
ospfd_options="  -A 127.0.0.1"
ospf6d_options=" -A ::1"
ripd_options="   -A 127.0.0.1"
ripngd_options=" -A ::1"
isisd_options="  -A 127.0.0.1"
pimd_options="   -A 127.0.0.1"
ldpd_options="   -A 127.0.0.1"
nhrpd_options="  -A 127.0.0.1"
eigrpd_options=" -A 127.0.0.1"
babeld_options=" -A 127.0.0.1"
sharpd_options=" -A 127.0.0.1"
pbrd_options="   -A 127.0.0.1"
staticd_options="-A 127.0.0.1"
bfdd_options="   -A 127.0.0.1"
fabricd_options="-A 127.0.0.1"

# The list of daemons to watch is automatically generated by the init script.
#watchfrr_options=""

# for debugging purposes, you can specify a "wrap" command to start instead
# of starting the daemon directly, e.g. to use valgrind on ospfd:
#   ospfd_wrap="/usr/bin/valgrind"
# or you can use "all_wrap" for all daemons, e.g. to use perf record:
#   all_wrap="/usr/bin/perf record --call-graph -"
# the normal daemon command is added to this at the end.
"""


class FrrService(CoreService):
    """
    Parent class for FRR services. Defines properties and methods
    common to FRR's routing daemons.
    """

    name = None
    group = "FRR"
    dependencies = ("FRRzebra",)
    dirs = ()
    configs = ()
    startup = ()
    shutdown = ()
    meta = "The config file for this service can be found in the Zebra service."

    ipv4_routing = False
    ipv6_routing = False

    @staticmethod
    def routerid(node):
        """
        Helper to return the first IPv4 address of a node as its router ID.
        """
        for ifc in node.netifs():
            if hasattr(ifc, "control") and ifc.control is True:
                continue
            for a in ifc.addrlist:
                if a.find(".") >= 0:
                    return a.split("/")[0]
        # raise ValueError,  "no IPv4 address found for router ID"
        return "0.0.0.0"

    @staticmethod
    def rj45check(ifc):
        """
        Helper to detect whether interface is connected an external RJ45
        link.
        """
        if ifc.net:
            for peerifc in ifc.net.netifs():
                if peerifc == ifc:
                    continue
                if isinstance(peerifc, Rj45Node):
                    return True
        return False

    @classmethod
    def generate_config(cls, node, filename):
        return ""

    @classmethod
    def generatefrrifcconfig(cls, node, ifc):
        return ""

    @classmethod
    def generatefrrconfig(cls, node):
        return ""


class FRROspfv2(FrrService):
    """
    The OSPFv2 service provides IPv4 routing for wired networks. It does
    not build its own configuration file but has hooks for adding to the
    unified frr.conf file.
    """

    name = "FRROSPFv2"
    startup = ()
    shutdown = ("killall ospfd",)
    validate = ("pidof ospfd",)
    ipv4_routing = True

    @staticmethod
    def mtucheck(ifc):
        """
        Helper to detect MTU mismatch and add the appropriate OSPF
        mtu-ignore command. This is needed when e.g. a node is linked via a
        GreTap device.
        """
        if ifc.mtu != 1500:
            # a workaround for PhysicalNode GreTap, which has no knowledge of
            # the other nodes/nets
            return "  ip ospf mtu-ignore\n"
        if not ifc.net:
            return ""
        for i in ifc.net.netifs():
            if i.mtu != ifc.mtu:
                return "  ip ospf mtu-ignore\n"
        return ""

    @staticmethod
    def ptpcheck(ifc):
        """
        Helper to detect whether interface is connected to a notional
        point-to-point link.
        """
        if isinstance(ifc.net, PtpNet):
            return "  ip ospf network point-to-point\n"
        return ""

    @classmethod
    def generatefrrconfig(cls, node):
        cfg = "router ospf\n"
        rtrid = cls.routerid(node)
        cfg += "  router-id %s\n" % rtrid
        # network 10.0.0.0/24 area 0
        for ifc in node.netifs():
            if hasattr(ifc, "control") and ifc.control is True:
                continue
            for a in ifc.addrlist:
                if a.find(".") < 0:
                    continue
                net = ipaddress.Ipv4Prefix(a)
                cfg += "  network %s area 0\n" % net
        cfg += "!\n"
        return cfg

    @classmethod
    def generatefrrifcconfig(cls, node, ifc):
        return cls.mtucheck(ifc)
        # cfg = cls.mtucheck(ifc)
        # external RJ45 connections will use default OSPF timers
        # if cls.rj45check(ifc):
        #    return cfg
        # cfg += cls.ptpcheck(ifc)

        # return cfg + """\


# ip ospf hello-interval 2
#  ip ospf dead-interval 6
#  ip ospf retransmit-interval 5
# """


class FRROspfv3(FrrService):
    """
    The OSPFv3 service provides IPv6 routing for wired networks. It does
    not build its own configuration file but has hooks for adding to the
    unified frr.conf file.
    """

    name = "FRROSPFv3"
    startup = ()
    shutdown = ("killall ospf6d",)
    validate = ("pidof ospf6d",)
    ipv4_routing = True
    ipv6_routing = True

    @staticmethod
    def minmtu(ifc):
        """
        Helper to discover the minimum MTU of interfaces linked with the
        given interface.
        """
        mtu = ifc.mtu
        if not ifc.net:
            return mtu
        for i in ifc.net.netifs():
            if i.mtu < mtu:
                mtu = i.mtu
        return mtu

    @classmethod
    def mtucheck(cls, ifc):
        """
        Helper to detect MTU mismatch and add the appropriate OSPFv3
        ifmtu command. This is needed when e.g. a node is linked via a
        GreTap device.
        """
        minmtu = cls.minmtu(ifc)
        if minmtu < ifc.mtu:
            return "  ipv6 ospf6 ifmtu %d\n" % minmtu
        else:
            return ""

    @staticmethod
    def ptpcheck(ifc):
        """
        Helper to detect whether interface is connected to a notional
        point-to-point link.
        """
        if isinstance(ifc.net, PtpNet):
            return "  ipv6 ospf6 network point-to-point\n"
        return ""

    @classmethod
    def generatefrrconfig(cls, node):
        cfg = "router ospf6\n"
        rtrid = cls.routerid(node)
        cfg += "  router-id %s\n" % rtrid
        for ifc in node.netifs():
            if hasattr(ifc, "control") and ifc.control is True:
                continue
            cfg += "  interface %s area 0.0.0.0\n" % ifc.name
        cfg += "!\n"
        return cfg

    @classmethod
    def generatefrrifcconfig(cls, node, ifc):
        return cls.mtucheck(ifc)
        # cfg = cls.mtucheck(ifc)
        # external RJ45 connections will use default OSPF timers
        # if cls.rj45check(ifc):
        #    return cfg
        # cfg += cls.ptpcheck(ifc)

        # return cfg + """\


# ipv6 ospf6 hello-interval 2
#  ipv6 ospf6 dead-interval 6
#  ipv6 ospf6 retransmit-interval 5
# """


class FRRBgp(FrrService):
    """
    The BGP service provides interdomain routing.
    Peers must be manually configured, with a full mesh for those
    having the same AS number.
    """

    name = "FRRBGP"
    startup = ()
    shutdown = ("killall bgpd",)
    validate = ("pidof bgpd",)
    custom_needed = True
    ipv4_routing = True
    ipv6_routing = True

    @classmethod
    def generatefrrconfig(cls, node):
        cfg = "!\n! BGP configuration\n!\n"
        cfg += "! You should configure the AS number below,\n"
        cfg += "! along with this router's peers.\n!\n"
        cfg += "router bgp %s\n" % node.id
        rtrid = cls.routerid(node)
        cfg += "  bgp router-id %s\n" % rtrid
        cfg += "  redistribute connected\n"
        cfg += "! neighbor 1.2.3.4 remote-as 555\n!\n"
        return cfg


class FRRRip(FrrService):
    """
    The RIP service provides IPv4 routing for wired networks.
    """

    name = "FRRRIP"
    startup = ()
    shutdown = ("killall ripd",)
    validate = ("pidof ripd",)
    ipv4_routing = True

    @classmethod
    def generatefrrconfig(cls, node):
        cfg = """\
router rip
  redistribute static
  redistribute connected
  redistribute ospf
  network 0.0.0.0/0
!
"""
        return cfg


class FRRRipng(FrrService):
    """
    The RIP NG service provides IPv6 routing for wired networks.
    """

    name = "FRRRIPNG"
    startup = ()
    shutdown = ("killall ripngd",)
    validate = ("pidof ripngd",)
    ipv6_routing = True

    @classmethod
    def generatefrrconfig(cls, node):
        cfg = """\
router ripng
  redistribute static
  redistribute connected
  redistribute ospf6
  network ::/0
!
"""
        return cfg


class FRRBabel(FrrService):
    """
    The Babel service provides a loop-avoiding distance-vector routing
    protocol for IPv6 and IPv4 with fast convergence properties.
    """

    name = "FRRBabel"
    startup = ()
    shutdown = ("killall babeld",)
    validate = ("pidof babeld",)
    ipv6_routing = True

    @classmethod
    def generatefrrconfig(cls, node):
        cfg = "router babel\n"
        for ifc in node.netifs():
            if hasattr(ifc, "control") and ifc.control is True:
                continue
            cfg += "  network %s\n" % ifc.name
        cfg += "  redistribute static\n  redistribute ipv4 connected\n"
        return cfg

    @classmethod
    def generatefrrifcconfig(cls, node, ifc):
        if ifc.net and ifc.net.linktype == LinkTypes.WIRELESS.value:
            return "  babel wireless\n  no babel split-horizon\n"
        else:
            return "  babel wired\n  babel split-horizon\n"


class FRRpimd(FrrService):
    """
    PIM multicast routing based on XORP.
    """

    name = "FRRpimd"
    startup = ()
    shutdown = ("killall pimd",)
    validate = ("pidof pimd",)
    ipv4_routing = True

    @classmethod
    def generatefrrconfig(cls, node):
        ifname = "eth0"
        for ifc in node.netifs():
            if ifc.name != "lo":
                ifname = ifc.name
                break
        cfg = "router mfea\n!\n"
        cfg += "router igmp\n!\n"
        cfg += "router pim\n"
        cfg += "  !ip pim rp-address 10.0.0.1\n"
        cfg += "  ip pim bsr-candidate %s\n" % ifname
        cfg += "  ip pim rp-candidate %s\n" % ifname
        cfg += "  !ip pim spt-threshold interval 10 bytes 80000\n"
        return cfg

    @classmethod
    def generatefrrifcconfig(cls, node, ifc):
        return "  ip mfea\n  ip igmp\n  ip pim\n"
