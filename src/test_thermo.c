#include <zephyr/ztest.h>
#include "thermo.h"

static thermo_t t;

/* Put the machine in a known state, take one step, return heater command */
static bool step(thermo_state_t from, int16_t temp, bool ok, bool rst)
{
	t.state = from;
	return thermo_step(&t, temp, ok, rst);
}

/*
 * This suite covers every state and every transition, yet mutation
 * testing shows several guards are never the sole reason a transition
 * is blocked. Build with CONFIG_THERMO_TEST_IMPROVED=y to add the
 * thermo_improved suite, which kills the survivors.
 */

ZTEST(thermo, test_idle_to_heating)
{
	zassert_true(step(ST_IDLE, 150, true, false));
	zassert_equal(t.state, ST_HEATING);
}

ZTEST(thermo, test_heating_to_idle)
{
	zassert_false(step(ST_HEATING, 220, true, false));
	zassert_equal(t.state, ST_IDLE);
}

ZTEST(thermo, test_idle_overtemp)
{
	zassert_false(step(ST_IDLE, 400, true, false));
	zassert_equal(t.state, ST_LOCKOUT);
}

ZTEST(thermo, test_heating_overtemp)
{
	zassert_false(step(ST_HEATING, 400, true, false));
	zassert_equal(t.state, ST_LOCKOUT);
}

ZTEST(thermo, test_lockout_reset)
{
	zassert_false(step(ST_LOCKOUT, 150, true, true));
	zassert_equal(t.state, ST_IDLE);
}

ZTEST(thermo, test_sensor_fault)
{
	zassert_false(step(ST_IDLE, 200, false, false));
	zassert_equal(t.state, ST_FAULT);
}

ZTEST(thermo, test_fault_reset)
{
	zassert_false(step(ST_FAULT, 200, true, true));
	zassert_equal(t.state, ST_IDLE);
}

ZTEST_SUITE(thermo, NULL, NULL, NULL, NULL, NULL);

#ifdef CONFIG_THERMO_TEST_IMPROVED
/* Tests that kill the mutants the suite above lets survive */

ZTEST(thermo_improved, test_lockout_needs_reset)
{
	zassert_false(step(ST_LOCKOUT, 150, true, false));
	zassert_equal(t.state, ST_LOCKOUT);
}

ZTEST(thermo_improved, test_open_sensor_reads_cold)
{
	zassert_false(step(ST_IDLE, -500, true, false));
	zassert_equal(t.state, ST_FAULT);
}

ZTEST(thermo_improved, test_overtemp_boundary)
{
	zassert_false(step(ST_HEATING, T_OVERTEMP, true, false));
	zassert_equal(t.state, ST_LOCKOUT);
}

ZTEST(thermo_improved, test_hysteresis_band)
{
	zassert_true(step(ST_HEATING, 200, true, false));
	zassert_equal(t.state, ST_HEATING);
}

ZTEST(thermo_improved, test_sensor_above_range)
{
	zassert_false(step(ST_IDLE, T_MAX + 100, true, false));
	zassert_equal(t.state, ST_FAULT);
}

ZTEST(thermo_improved, test_sensor_range_limits_are_valid)
{
	zassert_true(step(ST_IDLE, T_MIN, true, false));
	zassert_equal(t.state, ST_HEATING);
	zassert_false(step(ST_IDLE, T_MAX, true, false));
	zassert_equal(t.state, ST_LOCKOUT);
}

ZTEST(thermo_improved, test_idle_overtemp_boundary)
{
	zassert_false(step(ST_IDLE, T_OVERTEMP, true, false));
	zassert_equal(t.state, ST_LOCKOUT);
}

ZTEST(thermo_improved, test_idle_band_lower_edge)
{
	zassert_false(step(ST_IDLE, T_SETPOINT - T_HYST, true, false));
	zassert_equal(t.state, ST_IDLE);
}

ZTEST(thermo_improved, test_heating_band_upper_edge)
{
	zassert_false(step(ST_HEATING, T_SETPOINT + T_HYST, true, false));
	zassert_equal(t.state, ST_IDLE);
}

ZTEST(thermo_improved, test_reset_ignored_while_heating)
{
	zassert_true(step(ST_HEATING, 150, true, true));
	zassert_equal(t.state, ST_HEATING);
}

ZTEST(thermo_improved, test_lockout_reset_needs_cooling)
{
	zassert_false(step(ST_LOCKOUT, T_SETPOINT, true, true));
	zassert_equal(t.state, ST_LOCKOUT);
}

ZTEST(thermo_improved, test_fault_latches_without_reset)
{
	zassert_false(step(ST_FAULT, 200, true, false));
	zassert_equal(t.state, ST_FAULT);
}

ZTEST(thermo_improved, test_reset_with_bad_sensor)
{
	zassert_false(step(ST_FAULT, 200, false, true));
	zassert_equal(t.state, ST_FAULT);
}

ZTEST_SUITE(thermo_improved, NULL, NULL, NULL, NULL, NULL);
#endif
