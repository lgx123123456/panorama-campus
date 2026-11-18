shader_type spatial;
render_mode unshaded, blend_mix, cull_disabled, depth_draw_never, fog_disabled;

void fragment() {
	float d = length(UV * 2.0 - 1.0);
	float edge = 1.0 - smoothstep(0.98, 1.0, d);
	float rim = smoothstep(0.87, 0.94, d) * edge;
	float pulse = 0.5 + 0.5 * sin(TIME * 2.2);
	ALBEDO = mix(vec3(1.0, 0.65, 0.025), vec3(1.0, 0.88, 0.26), rim);
	ALPHA = edge * mix(0.30 + 0.06 * pulse, 0.92, rim);
}
