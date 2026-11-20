import json
import time

from ..instruments_base import BaseInstrument, BaseDevice, ChoiceSimpleMap, MemoryDevice
from ..instruments_registry import register_instrument

requests = None
def load_requests():
    global requests
    try:
        import requests
    except ImportError:
        raise RuntimeError("Package requests is required for this driver but it is currently missing. It can be installed with: pip install requests")
    return requests


class MontanaDev(BaseDevice):
    def __init__(self, get_name, set_name=None, get_func=None, set_func=None, **kwargs):
        load_requests()
        super(MontanaDev, self).__init__(**kwargs)
        self._getdev_p = get_name
        self._setdev_p = set_name
        self.get_func = get_func
        self.set_func = set_func

    def _setdev(self, val, **kwarg):
        self.set_func(val, **kwarg)

    def _getdev(self, **kwarg):
        return self.get_func(**kwarg)


class MontanaApiError(Exception):
    """A Montana API Error Exception"""

    def __init__(self, operation, path, response_code, brief, details):
        """Creates an error object.
        Keyword arguments:
           op            -- REST operation that triggered the error (e.g. "GET").
           path          -- The URI that triggered the error.
           response_code -- The HTTP response code (e.g. 400)
           brief            A synopsis of the problem.  Often it is the
                            contents of the "title" field of message content.
           details       -- A description of the problem.  Often it is the
                            contents of the "detail" field of message content.
        """
        self.operation = operation
        self.path = path
        self.response_code = response_code
        self.brief = brief
        self.details = details

    def __str__(self):
        result = "ApiError: {}: {}".format(self.operation, self.response_code)
        if self.brief:
            result = result.append(": {}").format(self.brief)
        return result


class MontanaBaseInstrument(BaseInstrument):
    _success_code = range(200, 300)

    def __init__(self, ip, port, api_version, *args, **kwargs):
        self.ip = ip
        self.port = port
        self.api_version = api_version
        super(MontanaBaseInstrument, self).__init__(*args, **kwargs)

    def __del__(self):
        self.ip = None
        self.port = None
        self.api_version = None
        super(MontanaBaseInstrument, self).__del__()

    def _root(self):
        return "http://{}:{}/{}".format(self.ip, self.port, self.api_version)

    def _url(self, path):
        root = self._root()
        path = path.strip("/").replace("//", "/")
        return "{}/{}".format(root, path)

    def _verify_request(operation, path, response):
        if response.status_code not in MontanaBaseInstrument._success_code:
            brief = None
            details = None
            try:
                if "title" in response.json().keys():
                    brief = response.json()["title"]
                if "detail" in response.json().keys():
                    details = response.json()["detail"]
            except:
                pass
            raise MontanaApiError(operation, path, response.status_code, brief, details)

    def _get(self, path, params=None):
        uri = self._url(path)
        response = requests.get(uri, params)
        MontanaBaseInstrument._verify_request("GET", path, response)
        content = response.content.decode("utf-8")
        if content != "":
            return json.loads(content)

    def _put(self, path, data=None):
        uri = self._url(path)
        response = requests.put(uri, json=data)
        MontanaBaseInstrument._verify_request("PUT", path, response)
        content = response.content.decode("utf-8")
        if content != "":
            return json.loads(content)

    def _post(self, path, data=None):
        uri = self._url(path)
        if data is not None:
            response = requests.post(uri, json=data)
        else:
            response = requests.post(uri)
        MontanaBaseInstrument._verify_request("POST", path, response)
        content = response.content.decode("utf-8")
        if content != "":
            return json.loads(content)


@register_instrument("Montana", "Cryostation")
class MontanaCryostation(MontanaBaseInstrument):
    """
    This controls the Montana Cryostation.
    Useful devices:
        Get/Set devices :
            platform_target_temperature
            pull_vacuum_target_pressure
            platform_bakeout_enabled
            platform_bakeout_temperature
            platform_bakeout_time
            platform_stability_target
            dry_nitrogen_purge_enabled
            dry_nitrogen_purge_num_times
            vent_continuously_enabled
            user1_stability_target
            user1_temperature_controller_enabled
            user1_target_temperature
            user2_stability_target
            user2_temperature_controller_enabled
            user2_target_temperature
        Get devices :
            all
            temperatures
            sample_chamber_pressure
            platform_temperature
            stage1_temperature
            stage2_temperature
            user1_temperature
            user2_temperature
            system_goal
            system_state
        Get sample devices :
            sample_chamber_pressure_sample
            platform_temperature_sample
            platform_heater_sample
            stage1_temperature_sample
            stage2_temperature_sample
            user1_temperature_sample
            user2_temperature_sample
            user1_heater_sample
            user2_heater_sample
    Useful methods:
        cooldown
        warmup
        vent
        pull_vacuum
        stop
    Feel free to add other devices by looking at the various get "sample" devices,
    as they provide informations about the cryostation.
    """

    def __init__(
        self, ip="192.168.137.252", port=47101, api_version="v1", *args, **kwargs
    ):
        super(MontanaCryostation, self).__init__(ip, port, api_version, *args, **kwargs)

    def __del__(self):
        super(MontanaCryostation, self).__del__()

    def _create_devs(self):
        self.platform_target_temperature = MontanaDev(
            get_name="get_platform_target_temperature",
            set_name="set_platform_target_temperature",
            get_func=self._get_platform_target_temperature,
            set_func=self._set_platform_target_temperature,
            doc="Platform target temperature in Kelvin.",
        )
        self.pull_vacuum_target_pressure = MontanaDev(
            get_name="get_pull_vacuum_target_pressure",
            set_name="set_pull_vacuum_target_pressure",
            get_func=self._get_pull_vacuum_target_pressure,
            set_func=self._set_pull_vacuum_target_pressure,
            doc="Pull vacuum target pressure in Pa.",
        )
        self.sample_chamber_pressure = MontanaDev(
            get_name="get_sample_chamber_pressure",
            get_func=self._get_sample_chamber_pressure,
            doc="Sample chamber pressure in Pa.",
        )
        self.platform_temperature = MontanaDev(
            get_name="get_platform_temperature",
            get_func=self._get_platform_temperature,
            doc="Platform temperature in Kelvin.",
        )
        self.stage1_temperature = MontanaDev(
            get_name="get_stage1_temperature",
            get_func=self._get_stage1_temperature,
            doc="Stage 1 temperature in Kelvin.",
        )
        self.stage2_temperature = MontanaDev(
            get_name="get_stage2_temperature",
            get_func=self._get_stage2_temperature,
            doc="Stage 2 temperature in Kelvin.",
        )
        self.user1_temperature = MontanaDev(
            get_name="get_user1_temperature",
            get_func=self._get_user1_temperature,
            doc="User 1 temperature in Kelvin.",
        )
        self.user2_temperature = MontanaDev(
            get_name="get_user2_temperature",
            get_func=self._get_user2_temperature,
            doc="User 2 temperature in Kelvin.",
        )
        self.system_goal = MontanaDev(
            get_name="get_system_goal",
            get_func=self._get_system_goal,
            doc="""String indicating the current system goal."
            Goals are 'None', 'PullVaccuum', 'Vent', 'Cooldown' and 'Warmup'.""",
        )
        self.system_state = MontanaDev(
            get_name="get_system_state",
            get_func=self._get_system_state,
            doc="""String indicating the current system state. States are :
            'Invalid', 'Idle', 'Configuring", 'Ready', 'WaitingForVacuumSystem',
            'CheckingForLeaks', 'BakeoutPreheating', 'BakingOut', 'Purging', 'PullingVacuum',
            'CoolingDown', 'AcquiringTarget', 'StableAtTarget', 'WarmingUp' and 'Venting'.""",
        )
        self.platform_bakeout_enabled = MontanaDev(
            get_name="get_platform_bakeout_enabled",
            set_name="set_platform_bakeout_enabled",
            get_func=self._get_platform_bakeout_enabled,
            set_func=self._set_platform_bakeout_enabled,
            doc="Device to control the bakeout. True if enabled.",
        )
        self.platform_bakeout_temperature = MontanaDev(
            get_name="get_platform_bakeout_temperature",
            set_name="set_platform_bakeout_temperature",
            get_func=self._get_platform_bakeout_temperature,
            set_func=self._set_platform_bakeout_temperature,
            doc="Platform bakeout temperature in Kelvin.",
        )
        self.platform_bakeout_time = MontanaDev(
            get_name="get_platform_bakeout_time",
            set_name="set_platform_bakeout_time",
            get_func=self._get_platform_bakeout_time,
            set_func=self._set_platform_bakeout_time,
            doc="Platform bakeout time in seconds.",
        )
        self.platform_stability_target = MontanaDev(
            get_name="get_platform_stability_target",
            set_name="set_platform_stability_target",
            get_func=self._get_platform_stability_target,
            set_func=self._set_platform_stability_target,
            doc="Platform stability target.",
        )
        self.dry_nitrogen_purge_enabled = MontanaDev(
            get_name="get_dry_nitrogen_purge_enabled",
            set_name="set_dry_nitrogen_purge_enabled",
            get_func=self._get_dry_nitrogen_purge_enabled,
            set_func=self._set_dry_nitrogen_purge_enabled,
            doc="Device to control the nitrogen purge. True if enabled.",
        )
        self.dry_nitrogen_purge_num_times = MontanaDev(
            get_name="get_dry_nitrogen_purge_num_times",
            set_name="set_dry_nitrogen_purge_num_times",
            get_func=self._get_dry_nitrogen_purge_num_times,
            set_func=self._set_dry_nitrogen_purge_num_times,
            doc="Device to control the number of dry nitrogen purge.",
        )
        self.vent_continuously_enabled = MontanaDev(
            get_name="get_vent_continuously_enabled",
            set_name="set_vent_continuously_enabled",
            get_func=self._get_vent_continuously_enabled,
            set_func=self._set_vent_continuously_enabled,
            doc="Device to control the continuous venting. True if enabled.",
        )
        self.sample_chamber_pressure_sample = MontanaDev(
            get_name="get_sample_chamber_pressure_sample",
            get_func=self._get_sample_chamber_pressure_sample,
            doc="Returns a dict of information regarding the sample chamber pressure.",
        )
        self.platform_temperature_sample = MontanaDev(
            get_name="get_platform_temperature_sample",
            get_func=self._get_platform_temperature_sample,
            doc="Returns a dict of information regarding the platform tempeature.",
        )
        self.platform_heater_sample = MontanaDev(
            get_name="get_platform_heater_sample",
            get_func=self._get_platform_heater_sample,
            doc="Returns a dict of information regarding the platform heater.",
        )
        self.stage1_temperature_sample = MontanaDev(
            get_name="get_stage1_temperature_sample",
            get_func=self._get_stage1_temperature_sample,
            doc="Returns a dict of information regarding the stage 1 temperature.",
        )
        self.stage2_temperature_sample = MontanaDev(
            get_name="get_stage2_temperature_sample",
            get_func=self._get_stage2_temperature_sample,
            doc="Returns a dict of information regarding the stage 2 temperature.",
        )
        self.user1_temperature_sample = MontanaDev(
            get_name="get_user1_temperature_sample",
            get_func=self._get_user1_temperature_sample,
            doc="Returns a dict of information regarding the user 1 temperature.",
        )
        self.user2_temperature_sample = MontanaDev(
            get_name="get_user2_temperature_sample",
            get_func=self._get_user2_temperature_sample,
            doc="Returns a dict of information regarding the user 2 temperature.",
        )
        self.user1_heater_sample = MontanaDev(
            get_name="get_user1_heater_sample",
            get_func=self._get_user1_heater_sample,
            doc="Returns a dict of information regarding the user 1 heater.",
        )
        self.user2_heater_sample = MontanaDev(
            get_name="get_user2_heater_sample",
            get_func=self._get_user2_heater_sample,
            doc="Returns a dict of information regarding the user 2 heater.",
        )
        self.user1_stability_target = MontanaDev(
            get_name="get_user1_stability_target",
            set_name="set_user1_stability_target",
            get_func=self._get_user1_stability_target,
            set_func=self._set_user1_stability_target,
            doc="User 1 stability target.",
        )
        self.user2_stability_target = MontanaDev(
            get_name="get_user2_stability_target",
            set_name="set_user2_stability_target",
            get_func=self._get_user2_stability_target,
            set_func=self._set_user2_stability_target,
            doc="User 2 stability target.",
        )
        self.user1_temperature_controller_enabled = MontanaDev(
            get_name="get_user1_temperature_controller_enabled",
            set_name="set_user1_temperature_controller_enabled",
            get_func=self._get_user1_temperature_controller_enabled,
            set_func=self._set_user1_temperature_controller_enabled,
            doc="User 1 temperature controller. True if enabled.",
        )

        self.user2_temperature_controller_enabled = MontanaDev(
            get_name="get_user2_temperature_controller_enabled",
            set_name="set_user2_temperature_controller_enabled",
            get_func=self._get_user2_temperature_controller_enabled,
            set_func=self._set_user2_temperature_controller_enabled,
            doc="User 2 temperature controller. True if enabled.",
        )

        self.user1_target_temperature = MontanaDev(
            get_name="get_user1_target_temperature",
            set_name="set_user1_target_temperature",
            get_func=self._get_user1_target_temperature,
            set_func=self._set_user1_target_temperature,
            doc="User 1 target temperature in Kelvin.",
        )

        self.user2_target_temperature = MontanaDev(
            get_name="get_user2_target_temperature",
            set_name="set_user2_target_temperature",
            get_func=self._get_user2_target_temperature,
            set_func=self._set_user2_target_temperature,
            doc="User 2 target temperature in Kelvin.",
        )

        self.temperatures = MontanaDev(
            get_name="get_temperatures",
            get_func=self._get_temperatures,
            doc="""Tuple containing the following temperatures in the following order:
                                       Platform, Stage1, Stage2, User1, User2.""",
        )
        self.all = MontanaDev(
            get_name="get_all",
            get_func=self._get_all,
            doc="""Tuple containing all the temperatures and the pressure sensor in the following order:
                              Platform, Stage1, Stage2, User1, User2, Chamber.""",
        )
        return super(MontanaCryostation, self)._create_devs()

    def cooldown(self):
        self._post("/controller/methods/cooldown()")

    def warmup(self):
        self._post("/controller/methods/warmup()")

    def vent(self):
        self._post("/controller/methods/vent()")

    def pull_vacuum(self):
        self._post("/controller/methods/pullVacuum()")

    def stop(self):
        self._post("/controller/methods/abortGoal()")

    def _get_platform_target_temperature(self):
        return self._get("/controller/properties/platformTargetTemperature")[
            "platformTargetTemperature"
        ]

    def _set_platform_target_temperature(self, target):
        return self._put("/controller/properties/platformTargetTemperature", target)

    def _get_pull_vacuum_target_pressure(self):
        return self._get("/controller/properties/pullVacuumTargetPressure")[
            "pullVacuumTargetPressure"
        ]

    def _set_pull_vacuum_target_pressure(self, target):
        return self._put("/controller/properties/pullVacuumTargetPressure", target)

    def _get_sample_chamber_pressure(self):
        return self._get(
            "/vacuumSystem/vacuumGauges/sampleChamberPressure/properties/pressureSample"
        )["pressureSample"]["pressure"]

    def _get_platform_temperature(self):
        return self._get(
            "/sampleChamber/temperatureControllers/platform/thermometer/properties/sample"
        )["sample"]["temperature"]

    def _get_stage1_temperature(self):
        return self._get(
            "/cooler/temperatureControllers/stage1/thermometer/properties/sample"
        )["sample"]["temperature"]

    def _get_stage2_temperature(self):
        return self._get(
            "/cooler/temperatureControllers/stage2/thermometer/properties/sample"
        )["sample"]["temperature"]

    def _get_user1_temperature(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user1/thermometer/properties/sample"
        )["sample"]["temperature"]

    def _get_user2_temperature(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user2/thermometer/properties/sample"
        )["sample"]["temperature"]

    def _get_temperatures(self):
        return (
            self.platform_temperature.get(),
            self.stage1_temperature.get(),
            self.stage2_temperature.get(),
            self.user1_temperature.get(),
            self.user2_temperature.get(),
        )

    def _get_all(self):
        return self._get_temperatures() + tuple([self.sample_chamber_pressure.get()])

    def _get_system_goal(self):
        return self._get("/controller/properties/systemGoal")["systemGoal"]

    def _get_system_state(self):
        return self._get("/controller/properties/systemState")["systemState"]

    def _get_platform_bakeout_enabled(self):
        return self._get("/controller/properties/platformBakeoutEnabled")[
            "platformBakeoutEnabled"
        ]

    def _set_platform_bakeout_enabled(self, enabled):
        return self._put("/controller/properties/platformBakeoutEnabled", enabled)

    def _get_platform_bakeout_temperature(self):
        return self._get("/controller/properties/platformBakeoutTemperature")[
            "platformBakeoutTemperature"
        ]

    def _set_platform_bakeout_temperature(self, temperature):
        return self._put(
            "/controller/properties/platformBakeoutTemperature", temperature
        )

    def _get_platform_bakeout_time(self):
        return self._get("/controller/properties/platformBakeoutTime")[
            "platformBakeoutTime"
        ]

    def _set_platform_bakeout_time(self, duration):
        return self._put("/controller/properties/platformBakeoutTime", duration)

    def _get_platform_stability_target(self):
        return self._get(
            "/sampleChamber/temperatureControllers/platform/thermometer/properties/stabilityTarget"
        )["stabilityTarget"]

    def _set_platform_stability_target(self, target):
        return self._put(
            "/sampleChamber/temperatureControllers/platform/thermometer/properties/stabilityTarget",
            target,
        )

    def _get_dry_nitrogen_purge_enabled(self):
        return self._get("/controller/properties/dryNitrogenPurgeEnabled")[
            "dryNitrogenPurgeEnabled"
        ]

    def _set_dry_nitrogen_purge_enabled(self, enabled):
        return self._put("/controller/properties/dryNitrogenPurgeEnabled", enabled)

    def _get_dry_nitrogen_purge_num_times(self):
        return self._get("/controller/properties/dryNitrogenPurgeNumTimes")[
            "dryNitrogenPurgeNumTimes"
        ]

    def _set_dry_nitrogen_purge_num_times(self, times):
        return self._put("/controller/properties/dryNitrogenPurgeNumTimes", times)

    def _get_vent_continuously_enabled(self):
        return self._get("/controller/properties/ventContinuouslyEnabled")[
            "ventContinuouslyEnabled"
        ]

    def _set_vent_continuously_enabled(self, enabled):
        return self._put("/controller/properties/ventContinuouslyEnabled", enabled)

    def _get_sample_chamber_pressure_sample(self):
        return self._get(
            "/vacuumSystem/vacuumGauges/sampleChamberPressure/properties/pressureSample"
        )["pressureSample"]

    def _get_platform_temperature_sample(self):
        return self._get(
            "/sampleChamber/temperatureControllers/platform/thermometer/properties/sample"
        )["sample"]

    def _get_platform_heater_sample(self):
        return self._get(
            "/sampleChamber/temperatureControllers/platform/heater/properties/sample"
        )["sample"]

    def _get_stage1_temperature_sample(self):
        return self._get(
            "/cooler/temperatureControllers/stage1/thermometer/properties/sample"
        )["sample"]

    def _get_stage2_temperature_sample(self):
        return self._get(
            "/cooler/temperatureControllers/stage2/thermometer/properties/sample"
        )["sample"]

    def _get_user1_temperature_sample(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user1/thermometer/properties/sample"
        )["sample"]

    def _get_user1_heater_sample(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user1/heater/properties/sample"
        )["sample"]

    def _get_user2_temperature_sample(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user2/thermometer/properties/sample"
        )["sample"]

    def _get_user2_heater_sample(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user2/heater/properties/sample"
        )["sample"]

    def _get_user1_stability_target(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user1/thermometer/properties/stabilityTarget"
        )["stabilityTarget"]

    def _set_user1_stability_target(self, target):
        return self._put(
            "/sampleChamber/temperatureControllers/user1/thermometer/properties/stabilityTarget",
            target,
        )

    def _get_user1_temperature_controller_enabled(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user1/properties/controllerEnabled"
        )["controllerEnabled"]

    def _set_user1_temperature_controller_enabled(self, enabled):
        return self._put(
            "/sampleChamber/temperatureControllers/user1/properties/controllerEnabled",
            enabled,
        )

    def _get_user1_target_temperature(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user1/properties/targetTemperature"
        )["targetTemperature"]

    def _set_user1_target_temperature(self, target):
        return self._put(
            "/sampleChamber/temperatureControllers/user1/properties/targetTemperature",
            target,
        )

    def _get_user2_stability_target(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user2/thermometer/properties/stabilityTarget"
        )["stabilityTarget"]

    def _set_user2_stability_target(self, target):
        return self._put(
            "/sampleChamber/temperatureControllers/user2/thermometer/properties/stabilityTarget",
            target,
        )

    def _get_user2_temperature_controller_enabled(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user2/properties/controllerEnabled"
        )["controllerEnabled"]

    def _set_user2_temperature_controller_enabled(self, enabled):
        return self._put(
            "/sampleChamber/temperatureControllers/user2/properties/controllerEnabled",
            enabled,
        )

    def _get_user2_target_temperature(self):
        return self._get(
            "/sampleChamber/temperatureControllers/user2/properties/targetTemperature"
        )["targetTemperature"]

    def _set_user2_target_temperature(self, target):
        return self._put(
            "/sampleChamber/temperatureControllers/user2/properties/targetTemperature",
            target,
        )


@register_instrument("Montana", "Rook")
class MontanaRook(MontanaBaseInstrument):
    """
    This controls the Montana Rook nanopositioner, Not fully tested, use at own risk!
    Useful devices:
        pos_x
        pos_y
        poy_z
        ax_status
        ax_pos
        ax_velocity
        ax_moving
        current_ax
    Useful methods:
        ax_stop
        ax_reset_encoder
        stop
    """

    # Todo : Step
    # Todo : Test ax memory device
    # Todo : Check for encoder thing if it works with a_pos
    # Todo : docs and check for units
    # Tester les devices multiples pour le cryo
    def __init__(
        self,
        ip="192.168.137.252",
        port=47171,
        api_version="v1",
        stack=1,
        *args,
        **kwargs
    ):
        self.stack = stack
        self._ax_to_id = {
            "z": 1,
            "x": 2,
            "y": 3,
        }
        super(MontanaRook, self).__init__(ip, port, api_version, *args, **kwargs)

    def _create_devs(self):
        self.current_ax = MemoryDevice(
            1,
            choices=ChoiceSimpleMap(
                self._ax_to_id,
                keys_values_lists=(self._ax_to_id.keys(), self._ax_to_id.values()),
                allow_keys=True
            ),
        )
        self.ax_status = MontanaDev(
            get_name="get_ax_status", get_func=self._get_ax_status
        )
        self.ax_moving = MontanaDev(
            get_name="get_ax_moving", get_func=self._get_ax_moving
        )
        self.ax_pos = MontanaDev(
            get_name="get_ax_pos",
            set_name="set_ax_pos",
            get_func=self._get_ax_encoder_position,
            set_func=self._move_ax_abs,
        )
        self.ax_velocity = MontanaDev(
            get_name="get_ax_velocity",
            set_name="set_ax_velocity",
            get_func=self._get_ax_velocity,
            set_func=self._set_ax_velocity,
        )
        self.pos_x = MontanaDev(
            get_name="get_pos_x",
            set_name="set_pos_x",
            get_func=lambda: self._get_ax_encoder_position("x"),
            set_func=lambda pos: self._move_ax_abs(pos=pos, ax="x"),
        )
        self.pos_y = MontanaDev(
            get_name="get_pos_y",
            set_name="set_pos_y",
            get_func=lambda: self._get_ax_encoder_position("y"),
            set_func=lambda pos: self._move_ax_abs(pos, ax="y"),
        )
        self.pos_z = MontanaDev(
            get_name="get_pos_z",
            set_name="set_pos_z",
            get_func=lambda: self._get_ax_encoder_position("z"),
            set_func=lambda pos: self._move_ax_abs(pos=pos, ax="z"),
        )
        return super()._create_devs()

    def __del__(self):
        super(MontanaRook, self).__del__()

    def _ax_helper(self, ax=None):
        if ax == None:
            return self.current_ax.get()
        if isinstance(ax, int):
            return ax
        if ax in self._ax_to_id.keys():
            return self._ax_to_id[ax]
        raise Exception(
            "ax {} not supported, choose between 'z', 'x', 'y' or '1', '2', '3'.".format(
                ax
            )
        )

    def _move_ax_abs(self, pos, ax=None, wait=True):
        """Move axis to an absolute position"""
        ax = self._ax_helper(ax)
        self._post(
            "stacks/stack{}/axes/axis{}/methods/moveAbsolute(double:pos)".format(
                self.stack, ax
            ),
            pos,
        )
        if wait:
            self._wait_for_ax(ax)

    def _wait_for_ax(self, ax=None, max_wait_s=60):
        """Returns True if the axis reached the target before timeout, False
        if timeout occurred and axis was still moving."""
        ax = self._ax_helper(ax)
        moving = True
        start_time = time.time()
        while moving:
            time.sleep(0.5)
            moving = self._get_ax_moving(self.stack, ax)

            elapsed_time = time.time() - start_time
            if moving and elapsed_time > max_wait_s:
                self.stop_axis(self.stack, ax)
                break
        return moving

    def _get_ax_status(self, ax=None):
        """Get the real-time status of the axis"""
        ax = self._ax_helper(ax)
        return self._get("stacks/stack{}/axes/axis{}/properties/status".format(self.stack, ax))[
            "status"
        ]

    def _get_ax_moving(self, ax=None):
        ax = self._ax_helper(ax)
        return self._get_ax_status(ax)["moving"]

    def _get_ax_encoder_position(self, ax=None):
        """Get the encoder position for the given axis."""
        ax = self._ax_helper(ax)
        return self._get_ax_status(ax)["targetPosition"]

    def _get_ax_velocity(self, ax=None):
        """Set the target velocity of the given axis"""
        ax = self._ax_helper(ax)
        return self._get("stacks/stack{}/axes/axis{}/properties/velocity".format(self.stack, ax))[
            "velocity"
        ]

    def _set_ax_velocity(self, ax=None, velocity=None):
        """Set the target velocity of the given axis"""
        ax = self._ax_helper(ax)
        self._put(
            "stacks/stack{}/axes/axis{}/properties/velocity".format(self.stack, ax), velocity
        )

    def ax_stop(self, ax=None):
        """Stop an axis"""
        ax = self._ax_helper(ax)
        self._post("stacks/stack{}/axes/axis{}/methods/stop()".format(self.stack, ax))

    def ax_reset_encoder(self, ax=None):
        """Zero the encoder position of an axis"""
        ax = self._ax_helper(ax)
        self._post("stacks/stack{}/axes/axis{}/methods/zero()".format(self.stack, ax))

    def stop(self):
        """Stop all axis"""
        self._post("controller/methods/emergencyStop()")
