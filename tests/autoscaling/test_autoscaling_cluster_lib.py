# Copyright 2015-2016 Yelp Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import contextlib

import mock
from botocore.exceptions import ClientError
from pytest import raises
from requests.exceptions import HTTPError

from paasta_tools.autoscaling import autoscaling_cluster_lib
from paasta_tools.mesos_tools import SlaveTaskCount
from paasta_tools.paasta_metastatus import ResourceInfo
from paasta_tools.utils import TimeoutError


def test_scale_aws_spot_fleet_request():
    with contextlib.nested(
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.filter_sfr_slaves', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.set_spot_fleet_request_capacity', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_mesos_master', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_mesos_task_count_by_slave', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.sort_slaves_to_kill', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.downscale_spot_fleet_request', autospec=True)
    ) as (
        mock_filter_sfr_slaves,
        mock_set_spot_fleet_request_capacity,
        mock_get_mesos_master,
        mock_get_mesos_task_count_by_slave,
        mock_sort_slaves_to_kill,
        mock_downscale_spot_fleet_request
    ):

        mock_sfr = mock.Mock()
        mock_resource = {'id': 'sfr-blah', 'sfr': mock_sfr, 'region': 'westeros-1', 'pool': 'default'}
        mock_pool_settings = {'drain_timeout': 123}
        mock_set_spot_fleet_request_capacity.return_value = True
        mock_master = mock.Mock()
        mock_mesos_state = mock.Mock()
        mock_master.state_summary.return_value = mock_mesos_state
        mock_get_mesos_master.return_value = mock_master

        # test no scale
        autoscaling_cluster_lib.scale_aws_spot_fleet_request(mock_resource, 4, 4, mock_pool_settings, False)
        assert not mock_set_spot_fleet_request_capacity.called

        # test scale up
        autoscaling_cluster_lib.scale_aws_spot_fleet_request(mock_resource, 2, 4, mock_pool_settings, False)
        mock_set_spot_fleet_request_capacity.assert_called_with('sfr-blah', 4, False, region='westeros-1')

        # test scale down
        mock_slave_1 = {'instance_weight': 1}
        mock_slave_2 = {'instance_weight': 2}
        mock_sfr_sorted_slaves_1 = [mock_slave_1, mock_slave_2]
        mock_filter_sfr_slaves.return_value = mock_sfr_sorted_slaves_1
        autoscaling_cluster_lib.scale_aws_spot_fleet_request(mock_resource, 5, 2, mock_pool_settings, False)
        assert mock_get_mesos_master.called
        mock_get_mesos_task_count_by_slave.assert_called_with(mock_mesos_state,
                                                              pool='default')
        mock_filter_sfr_slaves.assert_called_with(mock_get_mesos_task_count_by_slave.return_value, mock_resource)
        mock_downscale_spot_fleet_request.assert_called_with(resource=mock_resource,
                                                             filtered_slaves=mock_filter_sfr_slaves.return_value,
                                                             current_capacity=5,
                                                             target_capacity=2,
                                                             pool_settings=mock_pool_settings,
                                                             dry_run=False)


def test_downscale_spot_fleet_request():
    with contextlib.nested(
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_mesos_master', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_mesos_task_count_by_slave', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.sort_slaves_to_kill', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.gracefully_terminate_slave', autospec=True)
    ) as (
        mock_get_mesos_master,
        mock_get_mesos_task_count_by_slave,
        mock_sort_slaves_to_kill,
        mock_gracefully_terminate_slave
    ):
        mock_master = mock.Mock()
        mock_mesos_state = mock.Mock()
        mock_master.state_summary.return_value = mock_mesos_state
        mock_get_mesos_master.return_value = mock_master
        mock_slave_1 = {'hostname': 'host1', 'instance_id': 'i-blah123',
                        'instance_weight': 1}
        mock_slave_2 = {'hostname': 'host2', 'instance_id': 'i-blah456',
                        'instance_weight': 2}
        mock_resource = mock.Mock()
        mock_filtered_slaves = mock.Mock()
        mock_pool_settings = mock.Mock()
        mock_sfr_sorted_slaves_1 = [mock_slave_1, mock_slave_2]
        mock_sfr_sorted_slaves_2 = [mock_slave_2]
        mock_terminate_call_1 = mock.call(resource=mock_resource,
                                          slave_to_kill=mock_slave_1,
                                          pool_settings=mock_pool_settings,
                                          current_capacity=5,
                                          dry_run=False,
                                          new_capacity=4)
        mock_terminate_call_2 = mock.call(resource=mock_resource,
                                          slave_to_kill=mock_slave_2,
                                          pool_settings=mock_pool_settings,
                                          current_capacity=4,
                                          dry_run=False,
                                          new_capacity=2)
        # for draining slave 1 failure HTTPError scenario
        mock_terminate_call_3 = mock.call(resource=mock_resource,
                                          slave_to_kill=mock_slave_2,
                                          pool_settings=mock_pool_settings,
                                          current_capacity=5,
                                          dry_run=False,
                                          new_capacity=3)

        # test stop when reach capacity
        mock_sort_slaves_to_kill.return_value = mock_sfr_sorted_slaves_2
        autoscaling_cluster_lib.downscale_spot_fleet_request(resource=mock_resource,
                                                             filtered_slaves=mock_filtered_slaves,
                                                             pool_settings=mock_pool_settings,
                                                             current_capacity=5,
                                                             target_capacity=4,
                                                             dry_run=False)
        assert not mock_gracefully_terminate_slave.called

        # test stop if FailSetSpotCapacity
        mock_gracefully_terminate_slave.side_effect = autoscaling_cluster_lib.FailSetSpotCapacity
        mock_sfr_sorted_slaves_1 = [mock_slave_1, mock_slave_2]
        mock_sfr_sorted_slaves_2 = [mock_slave_2]
        mock_sort_slaves_to_kill.side_effect = iter([mock_sfr_sorted_slaves_1,
                                                     mock_sfr_sorted_slaves_2,
                                                     []])
        autoscaling_cluster_lib.downscale_spot_fleet_request(resource=mock_resource,
                                                             filtered_slaves=mock_filtered_slaves,
                                                             pool_settings=mock_pool_settings,
                                                             current_capacity=5,
                                                             target_capacity=2,
                                                             dry_run=False)
        mock_gracefully_terminate_slave.assert_has_calls([mock_terminate_call_1])

        # test continue if HTTPError
        mock_gracefully_terminate_slave.side_effect = HTTPError
        mock_gracefully_terminate_slave.reset_mock()
        mock_sfr_sorted_slaves_1 = [mock_slave_1, mock_slave_2]
        mock_sfr_sorted_slaves_2 = [mock_slave_2]
        mock_sort_slaves_to_kill.side_effect = iter([mock_sfr_sorted_slaves_1,
                                                     mock_sfr_sorted_slaves_2,
                                                     []])
        autoscaling_cluster_lib.downscale_spot_fleet_request(resource=mock_resource,
                                                             filtered_slaves=mock_filtered_slaves,
                                                             pool_settings=mock_pool_settings,
                                                             current_capacity=5,
                                                             target_capacity=2,
                                                             dry_run=False)
        mock_gracefully_terminate_slave.assert_has_calls([mock_terminate_call_1, mock_terminate_call_3])

        # test normal scale down
        mock_gracefully_terminate_slave.side_effect = None
        mock_gracefully_terminate_slave.reset_mock()
        mock_get_mesos_task_count_by_slave.reset_mock()
        mock_sort_slaves_to_kill.reset_mock()
        mock_sfr_sorted_slaves_1 = [mock_slave_1, mock_slave_2]
        mock_sfr_sorted_slaves_2 = [mock_slave_2]
        mock_sort_slaves_to_kill.side_effect = iter([mock_sfr_sorted_slaves_1,
                                                     mock_sfr_sorted_slaves_2,
                                                     []])
        autoscaling_cluster_lib.downscale_spot_fleet_request(resource=mock_resource,
                                                             filtered_slaves=mock_filtered_slaves,
                                                             pool_settings=mock_pool_settings,
                                                             current_capacity=5,
                                                             target_capacity=2,
                                                             dry_run=False)
        mock_sort_slaves_to_kill.assert_has_calls([mock.call(mock_filtered_slaves),
                                                   mock.call(mock_get_mesos_task_count_by_slave.return_value)])
        assert mock_get_mesos_master.called
        mock_gracefully_terminate_slave.assert_has_calls([mock_terminate_call_1, mock_terminate_call_2])
        mock_get_task_count_calls = [mock.call(mock_mesos_state, slaves_list=[mock_slave_2]),
                                     mock.call(mock_mesos_state, slaves_list=[])]
        mock_get_mesos_task_count_by_slave.assert_has_calls(mock_get_task_count_calls)

        # test non integer scale down
        # this should result in killing 3 instances,
        # leaving us on 7.1 provisioned of target 7
        mock_slave_1 = {'hostname': 'host1', 'instance_id': 'i-blah123',
                        'instance_weight': 0.3}
        mock_gracefully_terminate_slave.side_effect = None
        mock_gracefully_terminate_slave.reset_mock()
        mock_get_mesos_task_count_by_slave.reset_mock()
        mock_sort_slaves_to_kill.reset_mock()
        mock_sfr_sorted_slaves = [mock_slave_1] * 10
        mock_sort_slaves_to_kill.side_effect = iter([mock_sfr_sorted_slaves] +
                                                    [mock_sfr_sorted_slaves[x:-1] for x in range(0, 10)])
        autoscaling_cluster_lib.downscale_spot_fleet_request(resource=mock_resource,
                                                             filtered_slaves=mock_filtered_slaves,
                                                             pool_settings=mock_pool_settings,
                                                             current_capacity=8,
                                                             target_capacity=7,
                                                             dry_run=False)
        assert mock_gracefully_terminate_slave.call_count == 3


def test_gracefully_terminate_slave():
    with contextlib.nested(
        mock.patch('time.time', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.drain', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.undrain', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.set_spot_fleet_request_capacity', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.wait_and_terminate', autospec=True),
    ) as (
        mock_time,
        mock_drain,
        mock_undrain,
        mock_set_spot_fleet_request_capacity,
        mock_wait_and_terminate,
    ):
        mock_resource = {'id': 'sfr-blah', 'region': 'westeros-1'}
        mock_pool_settings = {'drain_timeout': 123}
        mock_time.return_value = int(1)
        mock_start = (1 + 123) * 1000000000
        mock_slave = {'hostname': 'host1', 'instance_id': 'i-blah123',
                      'pid': 'slave(1)@10.1.1.1:5051', 'instance_weight': 1,
                      'ip': '10.1.1.1'}
        autoscaling_cluster_lib.gracefully_terminate_slave(resource=mock_resource,
                                                           slave_to_kill=mock_slave,
                                                           pool_settings=mock_pool_settings,
                                                           current_capacity=5,
                                                           new_capacity=4,
                                                           dry_run=False)
        mock_drain.assert_called_with(['host1|10.1.1.1'], mock_start, 600 * 1000000000)
        set_call_1 = mock.call('sfr-blah', 4, False, region='westeros-1')
        mock_set_spot_fleet_request_capacity.assert_has_calls([set_call_1])
        mock_wait_and_terminate.assert_called_with(mock_slave, 123, False, region='westeros-1')
        mock_undrain.assert_called_with(['host1|10.1.1.1'])

        # test we cleanup if a termination fails
        set_call_2 = mock.call('sfr-blah', 5, False, region='westeros-1')
        mock_wait_and_terminate.side_effect = ClientError({'Error': {}}, 'blah')
        autoscaling_cluster_lib.gracefully_terminate_slave(resource=mock_resource,
                                                           slave_to_kill=mock_slave,
                                                           pool_settings=mock_pool_settings,
                                                           current_capacity=5,
                                                           new_capacity=4,
                                                           dry_run=False)
        mock_drain.assert_called_with(['host1|10.1.1.1'], mock_start, 600 * 1000000000)
        mock_set_spot_fleet_request_capacity.assert_has_calls([set_call_1, set_call_2])
        mock_wait_and_terminate.assert_called_with(mock_slave, 123, False, region='westeros-1')
        mock_undrain.assert_called_with(['host1|10.1.1.1'])

        # test we cleanup if a set spot capacity fails
        mock_wait_and_terminate.side_effect = None
        mock_wait_and_terminate.reset_mock()
        mock_set_spot_fleet_request_capacity.side_effect = autoscaling_cluster_lib.FailSetSpotCapacity
        with raises(autoscaling_cluster_lib.FailSetSpotCapacity):
            autoscaling_cluster_lib.gracefully_terminate_slave(resource=mock_resource,
                                                               slave_to_kill=mock_slave,
                                                               pool_settings=mock_pool_settings,
                                                               current_capacity=5,
                                                               new_capacity=4,
                                                               dry_run=False)
        mock_drain.assert_called_with(['host1|10.1.1.1'], mock_start, 600 * 1000000000)
        mock_set_spot_fleet_request_capacity.assert_has_calls([set_call_1])
        mock_undrain.assert_called_with(['host1|10.1.1.1'])
        assert not mock_wait_and_terminate.called

        # test we cleanup if a drain fails
        mock_wait_and_terminate.side_effect = None
        mock_set_spot_fleet_request_capacity.side_effect = None
        mock_set_spot_fleet_request_capacity.reset_mock()
        mock_drain.side_effect = HTTPError
        with raises(HTTPError):
            autoscaling_cluster_lib.gracefully_terminate_slave(resource=mock_resource,
                                                               slave_to_kill=mock_slave,
                                                               pool_settings=mock_pool_settings,
                                                               current_capacity=5,
                                                               new_capacity=4,
                                                               dry_run=False)
        mock_drain.assert_called_with(['host1|10.1.1.1'], mock_start, 600 * 1000000000)
        assert not mock_set_spot_fleet_request_capacity.called
        assert not mock_wait_and_terminate.called


def test_autoscale_local_cluster():
    with contextlib.nested(
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.load_system_paasta_config', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_cluster_metrics_provider', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_scaler', autospec=True),
    ) as (
        mock_get_paasta_config,
        mock_get_metrics_provider,
        mock_get_scaler,
    ):

        mock_scaling_resources = {'id1': {'id': 'sfr-blah', 'type': 'sfr', 'pool': 'default'}}
        mock_resource_pool_settings = {'default': {'drain_timeout': 123, 'target_utilization': 0.75}}
        mock_get_cluster_autoscaling_resources = mock.Mock(return_value=mock_scaling_resources)
        mock_get_resource_pool_settings = mock.Mock(return_value=mock_resource_pool_settings)
        mock_get_resources = mock.Mock(get_cluster_autoscaling_resources=mock_get_cluster_autoscaling_resources,
                                       get_resource_pool_settings=mock_get_resource_pool_settings)
        mock_get_paasta_config.return_value = mock_get_resources
        mock_metrics_provider = mock.Mock()
        mock_metrics_provider.return_value = (2, 6)
        mock_get_metrics_provider.return_value = mock_metrics_provider
        mock_scaler = mock.Mock()
        mock_get_scaler.return_value = mock_scaler

        # test scale up
        autoscaling_cluster_lib.autoscale_local_cluster()
        assert mock_get_paasta_config.called
        mock_get_metrics_provider.assert_called_with('sfr')
        mock_metrics_provider.assert_called_with('sfr-blah',
                                                 {'id': 'sfr-blah', 'type': 'sfr', 'pool': 'default'},
                                                 {'drain_timeout': 123, 'target_utilization': 0.75})
        mock_get_scaler.assert_called_with('sfr')
        mock_scaler.assert_called_with({'id': 'sfr-blah', 'type': 'sfr', 'pool': 'default'}, 2, 6,
                                       {'drain_timeout': 123, 'target_utilization': 0.75}, False)


def test_get_instances_from_ip():
    mock_instances = []
    ret = autoscaling_cluster_lib.get_instances_from_ip('10.1.1.1', mock_instances)
    assert ret == []

    mock_instances = [{'InstanceId': 'i-blah', 'PrivateIpAddress': '10.1.1.1'}]
    ret = autoscaling_cluster_lib.get_instances_from_ip('10.1.1.1', mock_instances)
    assert ret == mock_instances


def test_wait_and_terminate():
    with contextlib.nested(
        mock.patch('boto3.client', autospec=True),
        mock.patch('time.sleep', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.is_safe_to_kill', autospec=True),
    ) as (
        mock_ec2_client,
        _,
        mock_is_safe_to_kill,
    ):
        mock_terminate_instances = mock.Mock()
        mock_ec2_client.return_value = mock.Mock(terminate_instances=mock_terminate_instances)

        mock_is_safe_to_kill.return_value = True
        mock_slave_to_kill = {'ip': '10.1.1.1', 'instance_id': 'i-blah123', 'pid': 'slave(1)@10.1.1.1:5051',
                              'hostname': 'hostblah'}
        autoscaling_cluster_lib.wait_and_terminate(mock_slave_to_kill, 600, False, region='westeros-1')
        mock_terminate_instances.assert_called_with(InstanceIds=['i-blah123'], DryRun=False)
        mock_is_safe_to_kill.assert_called_with('hostblah')

        mock_is_safe_to_kill.side_effect = iter([False, False, True])
        autoscaling_cluster_lib.wait_and_terminate(mock_slave_to_kill, 600, False, region='westeros-1')
        assert mock_is_safe_to_kill.call_count == 4


def test_sort_slaves_to_kill():
    # test no slaves
    ret = autoscaling_cluster_lib.sort_slaves_to_kill({})
    assert ret == []

    mock_slave_1 = mock.Mock()
    mock_slave_2 = mock.Mock()
    mock_slave_3 = mock.Mock()
    mock_slave_1 = {'task_counts': SlaveTaskCount(count=3, slave=mock_slave_1, chronos_count=0)}
    mock_slave_2 = {'task_counts': SlaveTaskCount(count=2, slave=mock_slave_2, chronos_count=1)}
    mock_slave_3 = {'task_counts': SlaveTaskCount(count=5, slave=mock_slave_3, chronos_count=0)}
    mock_task_count = [mock_slave_1, mock_slave_2, mock_slave_3]
    ret = autoscaling_cluster_lib.sort_slaves_to_kill(mock_task_count)
    assert ret == [mock_slave_1, mock_slave_3, mock_slave_2]


def test_get_spot_fleet_instances():
    with contextlib.nested(
        mock.patch('boto3.client', autospec=True),
    ) as (
        mock_ec2_client,
    ):
        mock_instances = mock.Mock()
        mock_sfr = {'ActiveInstances': mock_instances}
        mock_describe_spot_fleet_instances = mock.Mock(return_value=mock_sfr)
        mock_ec2_client.return_value = mock.Mock(describe_spot_fleet_instances=mock_describe_spot_fleet_instances)
        ret = autoscaling_cluster_lib.get_spot_fleet_instances('sfr-blah', region='westeros-1')
        assert ret == mock_instances


def test_get_sfr_instance_ips():
    with contextlib.nested(
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.describe_instances', autospec=True),
    ) as (
        mock_describe_instances,
    ):
        mock_spot_fleet_instances = [{'InstanceId': 'i-blah1'}, {'InstanceId': 'i-blah2'}]
        mock_sfr = {'ActiveInstances': mock_spot_fleet_instances}
        mock_instances = [{'PrivateIpAddress': '10.1.1.1'}, {'PrivateIpAddress': '10.2.2.2'}]
        mock_describe_instances.return_value = mock_instances
        ret = autoscaling_cluster_lib.get_sfr_instance_ips(mock_sfr, region='westeros-1')
        mock_describe_instances.assert_called_with(['i-blah1', 'i-blah2'], region='westeros-1')
        assert ret == ['10.1.1.1', '10.2.2.2']


def test_get_sfr():
    with contextlib.nested(
        mock.patch('boto3.client', autospec=True),
    ) as (
        mock_ec2_client,
    ):
        mock_sfr_config = mock.Mock()
        mock_sfr = {'SpotFleetRequestConfigs': [mock_sfr_config]}
        mock_describe_spot_fleet_requests = mock.Mock(return_value=mock_sfr)
        mock_ec2_client.return_value = mock.Mock(describe_spot_fleet_requests=mock_describe_spot_fleet_requests)
        ret = autoscaling_cluster_lib.get_sfr('sfr-blah', region='westeros-1')
        mock_describe_spot_fleet_requests.assert_called_with(SpotFleetRequestIds=['sfr-blah'])
        assert ret == mock_sfr_config

        mock_error = {'Error': {'Code': 'InvalidSpotFleetRequestId.NotFound'}}
        mock_describe_spot_fleet_requests = mock.Mock(side_effect=ClientError(mock_error, 'blah'))
        mock_ec2_client.return_value = mock.Mock(describe_spot_fleet_requests=mock_describe_spot_fleet_requests)
        ret = autoscaling_cluster_lib.get_sfr('sfr-blah', region='westeros-1')
        assert ret is None


def test_filter_sfr_slaves():
    with contextlib.nested(
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_sfr_instance_ips', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.slave_pid_to_ip', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_instances_from_ip', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.describe_instances', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_instance_type_weights', autospec=True),
    ) as (
        mock_get_sfr_instance_ips,
        mock_pid_to_ip,
        mock_get_instances_from_ip,
        mock_describe_instances,
        mock_get_instance_type_weights
    ):
        mock_sfr = mock.Mock()
        mock_resource = {'sfr': mock_sfr, 'region': 'westeros-1'}
        mock_get_sfr_instance_ips.return_value = ['10.1.1.1', '10.3.3.3']
        mock_pid_to_ip.side_effect = iter(['10.1.1.1', '10.2.2.2', '10.3.3.3',
                                           '10.1.1.1', '10.3.3.3', '10.1.1.1', '10.3.3.3'])
        mock_get_instances_from_ip.side_effect = iter([[{'InstanceId': 'i-1'}], [{'InstanceId': 'i-3'}]])
        mock_instances = [{'InstanceId': 'i-1',
                           'InstanceType': 'c4.blah'},
                          {'InstanceId': 'i-2',
                           'InstanceType': 'm4.whatever'},
                          {'InstanceId': 'i-3',
                           'InstanceType': 'm4.whatever'}]
        mock_describe_instances.return_value = mock_instances
        mock_slave_1 = {'task_counts': SlaveTaskCount(slave={'pid': 'slave(1)@10.1.1.1:5051', 'id': '123',
                                                             'hostname': 'host123'},
                                                      count=0, chronos_count=0)}
        mock_slave_2 = {'task_counts': SlaveTaskCount(slave={'pid': 'slave(2)@10.2.2.2:5051', 'id': '456',
                                                             'hostname': 'host456'},
                                                      count=0, chronos_count=0)}
        mock_slave_3 = {'task_counts': SlaveTaskCount(slave={'pid': 'slave(3)@10.3.3.3:5051', 'id': '789',
                                                             'hostname': 'host789'},
                                                      count=0, chronos_count=0)}

        mock_sfr_sorted_slaves = [mock_slave_1, mock_slave_2, mock_slave_3]
        mock_get_instance_call_1 = mock.call('10.1.1.1', mock_instances)
        mock_get_instance_call_3 = mock.call('10.3.3.3', mock_instances)
        mock_get_ip_call_1 = mock.call('slave(1)@10.1.1.1:5051')
        mock_get_ip_call_2 = mock.call('slave(2)@10.2.2.2:5051')
        mock_get_ip_call_3 = mock.call('slave(3)@10.3.3.3:5051')
        mock_get_instance_type_weights.return_value = {'c4.blah': 2, 'm4.whatever': 5}
        ret = autoscaling_cluster_lib.filter_sfr_slaves(mock_sfr_sorted_slaves, mock_resource)
        mock_get_sfr_instance_ips.assert_called_with(mock_sfr, region='westeros-1')
        mock_pid_to_ip.assert_has_calls([mock_get_ip_call_1, mock_get_ip_call_2, mock_get_ip_call_3,
                                         mock_get_ip_call_1, mock_get_ip_call_3])
        mock_get_instances_from_ip.assert_has_calls([mock_get_instance_call_1, mock_get_instance_call_3])
        mock_describe_instances.assert_called_with([], region='westeros-1',
                                                   instance_filters=[{'Values': ['10.1.1.1', '10.3.3.3'],
                                                                      'Name': 'private-ip-address'}])
        mock_get_instance_type_weights.assert_called_with(mock_sfr)
        expected = [{'pid': 'slave(1)@10.1.1.1:5051',
                     'instance_id': 'i-1',
                     'id': '123',
                     'instance_type': 'c4.blah',
                     'task_counts': mock_slave_1['task_counts'],
                     'hostname': 'host123',
                     'ip': '10.1.1.1',
                     'instance_weight': 2},
                    {'pid': 'slave(3)@10.3.3.3:5051',
                     'instance_id': 'i-3',
                     'id': '789',
                     'instance_type': 'm4.whatever',
                     'task_counts': mock_slave_3['task_counts'],
                     'hostname': 'host789',
                     'ip': '10.3.3.3',
                     'instance_weight': 5}]
        assert ret == expected


def test_set_spot_fleet_request_capacity():
    with contextlib.nested(
        mock.patch('boto3.client', autospec=True),
        mock.patch('time.sleep', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_sfr', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.AWS_SPOT_MODIFY_TIMEOUT', autospec=True)
    ) as (
        mock_ec2_client,
        mock_sleep,
        mock_get_sfr,
        _
    ):
        mock_sleep.side_effect = TimeoutError()
        mock_get_sfr.return_value = {'SpotFleetRequestState': 'modifying'}
        mock_modify_spot_fleet_request = mock.Mock()
        mock_ec2_client.return_value = mock.Mock(modify_spot_fleet_request=mock_modify_spot_fleet_request)
        with raises(autoscaling_cluster_lib.FailSetSpotCapacity):
            ret = autoscaling_cluster_lib.set_spot_fleet_request_capacity('sfr-blah', 4, False, region='westeros-1')
        assert not mock_modify_spot_fleet_request.called

        mock_modify_spot_fleet_request.side_effect = ClientError({'Error': {}}, 'blah')
        mock_get_sfr.return_value = {'SpotFleetRequestState': 'active'}
        with raises(autoscaling_cluster_lib.FailSetSpotCapacity):
            ret = autoscaling_cluster_lib.set_spot_fleet_request_capacity('sfr-blah', 4, False, region='westeros-1')

        mock_modify_spot_fleet_request.side_effect = None
        ret = autoscaling_cluster_lib.set_spot_fleet_request_capacity('sfr-blah', 4, False, region='westeros-1')
        mock_modify_spot_fleet_request.assert_called_with(SpotFleetRequestId='sfr-blah',
                                                          TargetCapacity=4,
                                                          ExcessCapacityTerminationPolicy='noTermination')
        assert ret is not None


def test_get_instance_type_weights():
    mock_launch_specs = [{'InstanceType': 'c4.blah',
                          'WeightedCapacity': 123},
                         {'InstanceType': 'm4.whatever',
                          'WeightedCapacity': 456}]
    mock_sfr = {'SpotFleetRequestConfig': {'LaunchSpecifications': mock_launch_specs}}
    ret = autoscaling_cluster_lib.get_instance_type_weights(mock_sfr)
    assert ret == {'c4.blah': 123, 'm4.whatever': 456}


def test_describe_instance():
    with contextlib.nested(
        mock.patch('boto3.client', autospec=True),
    ) as (
        mock_ec2_client,
    ):
        mock_instance_1 = mock.Mock()
        mock_instance_2 = mock.Mock()
        mock_instances = {'Reservations': [{'Instances': [mock_instance_1]}, {'Instances': [mock_instance_2]}]}
        mock_describe_instances = mock.Mock(return_value=mock_instances)
        mock_ec2_client.return_value = mock.Mock(describe_instances=mock_describe_instances)
        ret = autoscaling_cluster_lib.describe_instances(['i-1', 'i-2'],
                                                         region='westeros-1',
                                                         instance_filters=['filter1'])
        mock_describe_instances.assert_called_with(InstanceIds=['i-1', 'i-2'], Filters=['filter1'])
        assert ret == [mock_instance_1, mock_instance_2]

        ret = autoscaling_cluster_lib.describe_instances(['i-1', 'i-2'], region='westeros-1')
        mock_describe_instances.assert_called_with(InstanceIds=['i-1', 'i-2'], Filters=[])

        mock_error = {'Error': {'Code': 'InvalidInstanceID.NotFound'}}
        mock_describe_instances.side_effect = ClientError(mock_error, 'blah')
        ret = autoscaling_cluster_lib.describe_instances(['i-1', 'i-2'], region='westeros-1')
        assert ret is None


def test_spotfleet_metrics_provider():
    with contextlib.nested(
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_sfr', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_spot_fleet_instances', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_sfr_instance_ips', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_resource_utilization_by_grouping',
                   autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.slave_pid_to_ip', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_spot_fleet_delta', autospec=True),
        mock.patch('paasta_tools.autoscaling.autoscaling_cluster_lib.get_mesos_master', autospec=True),
    ) as (
        mock_get_sfr,
        mock_get_spot_fleet_instances,
        mock_get_sfr_instance_ips,
        mock_get_resource_utilization_by_grouping,
        mock_pid_to_ip,
        mock_get_spot_fleet_delta,
        mock_get_mesos_master
    ):
        mock_resource = {'pool': 'default',
                         'region': 'westeros-1'}
        mock_mesos_state = {'slaves': [{'id': 'id1',
                                        'attributes': {'pool': 'default'},
                                        'pid': 'pid1'},
                                       {'id': 'id2',
                                        'attributes': {'pool': 'default'},
                                        'pid': 'pid2'}]}
        mock_master = mock.Mock(state=mock_mesos_state)
        mock_get_mesos_master.return_value = mock_master
        mock_utilization = {'free': ResourceInfo(cpus=5.0, mem=2048.0, disk=20.0),
                            'total': ResourceInfo(cpus=10.0, mem=4096.0, disk=40.0)}
        mock_get_resource_utilization_by_grouping.return_value = {'default': mock_utilization}
        mock_pid_to_ip.side_effect = iter(['10.1.1.1', '10.2.2.2'])
        mock_get_spot_fleet_instances.return_value = [mock.Mock(), mock.Mock()]
        mock_get_sfr_instance_ips.return_value = ['10.1.1.1', '10.2.2.2']
        mock_get_spot_fleet_delta.return_value = 1, 2
        mock_pool_settings = {}

        mock_get_sfr.return_value = {'SpotFleetRequestState': 'cancelled'}
        ret = autoscaling_cluster_lib.spotfleet_metrics_provider('sfr-blah', mock_resource, mock_pool_settings)
        mock_get_sfr.assert_called_with('sfr-blah', region='westeros-1')
        assert not mock_get_spot_fleet_instances.called
        assert ret == (0, 0)

        mock_get_sfr.return_value = None
        ret = autoscaling_cluster_lib.spotfleet_metrics_provider('sfr-blah', mock_resource, mock_pool_settings)
        mock_get_sfr.assert_called_with('sfr-blah', region='westeros-1')
        assert not mock_get_spot_fleet_instances.called
        assert ret == (0, 0)

        mock_get_sfr.return_value = {'SpotFleetRequestState': 'active'}
        ret = autoscaling_cluster_lib.spotfleet_metrics_provider('sfr-blah', mock_resource, mock_pool_settings)
        mock_get_sfr.assert_called_with('sfr-blah', region='westeros-1')
        mock_get_spot_fleet_instances.assert_called_with('sfr-blah', region='westeros-1')
        expected_get_ip_call = mock_get_sfr.return_value.copy()
        expected_get_ip_call['ActiveInstances'] = mock_get_spot_fleet_instances.return_value
        mock_get_sfr_instance_ips.assert_called_with(expected_get_ip_call, region='westeros-1')
        mock_pid_to_ip.assert_has_calls([mock.call('pid1'), mock.call('pid2')])
        mock_get_resource_utilization_by_grouping.assert_called_with(mock.ANY, mock_mesos_state)
        mock_get_spot_fleet_delta.assert_called_with(mock_resource, float(0.5) - float(0.8))
        assert ret == (1, 2)
