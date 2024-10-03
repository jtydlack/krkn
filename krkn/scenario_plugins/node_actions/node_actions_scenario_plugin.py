import logging
import time

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value, log_exception

from krkn import cerberus, utils
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.node_actions import common_node_functions
from krkn.scenario_plugins.node_actions.aws_node_scenarios import aws_node_scenarios
from krkn.scenario_plugins.node_actions.az_node_scenarios import azure_node_scenarios
from krkn.scenario_plugins.node_actions.docker_node_scenarios import (
    docker_node_scenarios,
)
from krkn.scenario_plugins.node_actions.gcp_node_scenarios import gcp_node_scenarios
from krkn.scenario_plugins.node_actions.general_cloud_node_scenarios import (
    general_node_scenarios,
)

node_general = False


class NodeActionsScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        with open(scenario, "r") as f:
            node_scenario_config = yaml.full_load(f)
            for node_scenario in node_scenario_config["node_scenarios"]:
                try:
                    node_scenario_object = self.get_node_scenario_object(
                        node_scenario, lib_telemetry.get_lib_kubernetes()
                    )
                    if node_scenario["actions"]:
                        for action in node_scenario["actions"]:
                            start_time = int(time.time())
                            self.inject_node_scenario(
                                action,
                                node_scenario,
                                node_scenario_object,
                                lib_telemetry.get_lib_kubernetes(),
                            )
                            end_time = int(time.time())
                            cerberus.get_status(krkn_config, start_time, end_time)
                except (RuntimeError, Exception) as e:
                    logging.error("Node Actions exiting due to Exception %s" % e)
                    return 1
                else:
                    return 0

    def get_node_scenario_object(self, node_scenario, kubecli: KrknKubernetes):
        if (
            "cloud_type" not in node_scenario.keys()
            or node_scenario["cloud_type"] == "generic"
        ):
            global node_general
            node_general = True
            return general_node_scenarios(kubecli)
        if node_scenario["cloud_type"] == "aws":
            return aws_node_scenarios(kubecli)
        elif node_scenario["cloud_type"] == "gcp":
            return gcp_node_scenarios(kubecli)
        elif node_scenario["cloud_type"] == "openstack":
            from krkn.scenario_plugins.node_actions.openstack_node_scenarios import (
                openstack_node_scenarios,
            )

            return openstack_node_scenarios(kubecli)
        elif (
            node_scenario["cloud_type"] == "azure"
            or node_scenario["cloud_type"] == "az"
        ):
            return azure_node_scenarios(kubecli)
        elif (
            node_scenario["cloud_type"] == "alibaba"
            or node_scenario["cloud_type"] == "alicloud"
        ):
            from krkn.scenario_plugins.node_actions.alibaba_node_scenarios import (
                alibaba_node_scenarios,
            )

            return alibaba_node_scenarios(kubecli)
        elif node_scenario["cloud_type"] == "bm":
            from krkn.scenario_plugins.node_actions.bm_node_scenarios import (
                bm_node_scenarios,
            )

            return bm_node_scenarios(
                node_scenario.get("bmc_info"),
                node_scenario.get("bmc_user", None),
                node_scenario.get("bmc_password", None),
                kubecli,
            )
        elif node_scenario["cloud_type"] == "docker":
            return docker_node_scenarios(kubecli)
        else:
            logging.error(
                "Cloud type "
                + node_scenario["cloud_type"]
                + " is not currently supported; "
                "try using 'generic' if wanting to stop/start kubelet or fork bomb on any "
                "cluster"
            )
            raise Exception(
                "Cloud type "
                + node_scenario["cloud_type"]
                + " is not currently supported; "
                "try using 'generic' if wanting to stop/start kubelet or fork bomb on any "
                "cluster"
            )

    def inject_node_scenario(
        self, action, node_scenario, node_scenario_object, kubecli: KrknKubernetes
    ):
        generic_cloud_scenarios = ("stop_kubelet_scenario", "node_crash_scenario")
        # Get the node scenario configurations
        run_kill_count = get_yaml_item_value(node_scenario, "runs", 1)
        instance_kill_count = get_yaml_item_value(node_scenario, "instance_count", 1)
        node_name = get_yaml_item_value(node_scenario, "node_name", "")
        label_selector = get_yaml_item_value(node_scenario, "label_selector", "")
        if action == "node_stop_start_scenario":
            duration = get_yaml_item_value(node_scenario, "duration", 120)
        timeout = get_yaml_item_value(node_scenario, "timeout", 120)
        service = get_yaml_item_value(node_scenario, "service", "")
        ssh_private_key = get_yaml_item_value(
            node_scenario, "ssh_private_key", "~/.ssh/id_rsa"
        )
        # Get the node to apply the scenario
        if node_name:
            node_name_list = node_name.split(",")
        else:
            node_name_list = [node_name]
        for single_node_name in node_name_list:
            nodes = common_node_functions.get_node(
                single_node_name, label_selector, instance_kill_count, kubecli
            )
            for single_node in nodes:
                if node_general and action not in generic_cloud_scenarios:
                    logging.info(
                        "Scenario: "
                        + action
                        + " is not set up for generic cloud type, skipping action"
                    )
                else:
                    if action == "node_start_scenario":
                        node_scenario_object.node_start_scenario(
                            run_kill_count, single_node, timeout
                        )
                    elif action == "node_stop_scenario":
                        node_scenario_object.node_stop_scenario(
                            run_kill_count, single_node, timeout
                        )
                    elif action == "node_stop_start_scenario":
                        node_scenario_object.node_stop_start_scenario(
                            run_kill_count, single_node, timeout, duration
                        )
                    elif action == "node_termination_scenario":
                        node_scenario_object.node_termination_scenario(
                            run_kill_count, single_node, timeout
                        )
                    elif action == "node_reboot_scenario":
                        node_scenario_object.node_reboot_scenario(
                            run_kill_count, single_node, timeout
                        )
                    elif action == "stop_start_kubelet_scenario":
                        node_scenario_object.stop_start_kubelet_scenario(
                            run_kill_count, single_node, timeout
                        )
                    elif action == "restart_kubelet_scenario":
                        node_scenario_object.restart_kubelet_scenario(
                            run_kill_count, single_node, timeout
                        )
                    elif action == "stop_kubelet_scenario":
                        node_scenario_object.stop_kubelet_scenario(
                            run_kill_count, single_node, timeout
                        )
                    elif action == "node_crash_scenario":
                        node_scenario_object.node_crash_scenario(
                            run_kill_count, single_node, timeout
                        )
                    elif action == "stop_start_helper_node_scenario":
                        if node_scenario["cloud_type"] != "openstack":
                            logging.error(
                                "Scenario: " + action + " is not supported for "
                                "cloud type "
                                + node_scenario["cloud_type"]
                                + ", skipping action"
                            )
                        else:
                            if not node_scenario["helper_node_ip"]:
                                logging.error("Helper node IP address is not provided")
                                raise Exception(
                                    "Helper node IP address is not provided"
                                )
                            node_scenario_object.helper_node_stop_start_scenario(
                                run_kill_count, node_scenario["helper_node_ip"], timeout
                            )
                            node_scenario_object.helper_node_service_status(
                                node_scenario["helper_node_ip"],
                                service,
                                ssh_private_key,
                                timeout,
                            )
                    else:
                        logging.info(
                            "There is no node action that matches %s, skipping scenario"
                            % action
                        )

    def get_scenario_types(self) -> list[str]:
        return ["node_scenarios"]
