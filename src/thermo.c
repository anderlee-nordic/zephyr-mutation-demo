#include "thermo.h"

bool thermo_step(thermo_t *t, int16_t temp, bool sensor_ok, bool reset_btn)
{
	bool valid = sensor_ok && temp >= T_MIN && temp <= T_MAX;

	if (!valid) {
		t->state = ST_FAULT;
	}

	switch (t->state) {
	case ST_IDLE:
		if (temp >= T_OVERTEMP) {
			t->state = ST_LOCKOUT;
		} else if (temp < T_SETPOINT - T_HYST) {
			t->state = ST_HEATING;
		}
		break;
	case ST_HEATING:
		if (temp >= T_OVERTEMP) {
			t->state = ST_LOCKOUT;
		} else if (temp >= T_SETPOINT + T_HYST) {
			t->state = ST_IDLE;
		}
		break;
	case ST_LOCKOUT:
		if (reset_btn && temp < T_SETPOINT) {
			t->state = ST_IDLE;
		}
		break;
	case ST_FAULT:
		if (reset_btn && valid) {
			t->state = ST_IDLE;
		}
		break;
	}

	return t->state == ST_HEATING;
}
