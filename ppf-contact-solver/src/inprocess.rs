use crate::{
    backend::Backend,
    builder,
    data::{BvhSet, DataSet, EdgeParam, EdgeProp, ParamSet, StepResult, Vec3fp},
    scene::Scene,
    triutils,
    ProgramArgs,
    SimArgs,
};
use more_asserts::*;
use na::Matrix3xX;
use std::collections::HashMap;
use std::ffi::CString;
use std::sync::mpsc;

extern crate nalgebra as na;

extern "C" {
    // Bind to namespaced ABI symbols to avoid collisions with libc (e.g. `advance`).
    #[link_name = "ppf_advance"]
    fn advance(result: *mut StepResult);
    #[link_name = "ppf_update_bvh"]
    fn update_bvh(bvhset: *const BvhSet);
    #[link_name = "ppf_update_dyn"]
    fn update_dyn(index: *const u32, offset: *const u32);
    #[link_name = "ppf_update_constraint"]
    fn update_constraint(constraint: *const crate::data::Constraint);
    #[link_name = "ppf_initialize"]
    fn initialize(data: *const DataSet, param: *const ParamSet) -> bool;
    #[link_name = "ppf_set_log_path"]
    fn set_log_path(data_dir: *const std::os::raw::c_char);
}

struct ContactThread {
    task_sender: mpsc::Sender<(Matrix3xX<f32>, na::Matrix3xX<usize>, na::Matrix2xX<usize>)>,
    result_receiver: mpsc::Receiver<BvhSet>,
    task_sent: bool,
}

/// In-process stepping wrapper around the upstream solver.
///
/// Design goals:
/// - Reuse the exact same Rust/CUDA core; no physics rewrite.
/// - Keep `DataSet` and `ParamSet` memory addresses stable across steps.
/// - Mirror `Backend::run` stepping semantics (constraint/param update, BVH update cadence).
pub struct InProcessSession {
    pub program_args: ProgramArgs,
    pub sim_args: SimArgs,
    pub scene: Scene,
    pub backend: Backend,
    dataset: Box<DataSet>,
    param: Box<ParamSet>,
    contact_thread: Option<ContactThread>,
}

impl InProcessSession {
    fn debug_enabled() -> bool {
        std::env::var("PPF_INPROCESS_DEBUG")
            .ok()
            .is_some_and(|v| v == "1" || v.eq_ignore_ascii_case("true"))
    }
    /// Creates a new session from a PPF scene folder.
    ///
    /// `program_args.path` must point at the scene directory. `program_args.output` is used
    /// only for the CUDA backend log path (data dir); the in-process runner itself does not
    /// write vert/state outputs.
    pub fn new(program_args: ProgramArgs) -> Result<Self, String> {
        if program_args.path.is_empty() {
            return Err("ProgramArgs.path must point to a scene folder".to_string());
        }

        if program_args.output.is_empty() {
            return Err("ProgramArgs.output must be a writable directory".to_string());
        }

        // Ensure output/data exists for CUDA-side logging.
        let data_dir_path = std::path::Path::new(program_args.output.as_str()).join("data");
        if let Err(e) = std::fs::create_dir_all(&data_dir_path) {
            return Err(format!("Failed to create output/data dir: {e}"));
        }
        let data_dir = CString::new(data_dir_path.to_string_lossy().to_string())
            .map_err(|e| format!("Invalid output/data path: {e}"))?;
        unsafe {
            set_log_path(data_dir.as_ptr());
        }

        let mut scene = Scene::new(&program_args);
        let sim_args = scene.args();

        if program_args.load > 0 {
            // Load path: load mesh + state and dataset written by the CLI.
            let mut param = builder::make_param(&sim_args);
            let dataset_path = format!("{}/dataset.bin.gz", program_args.output);
            let state_dir = program_args.output.clone();

            if !std::path::Path::new(&dataset_path).exists() {
                return Err(format!("Missing dataset file: {dataset_path}"));
            }
            let mut dataset: DataSet = crate::read(&crate::read_gz(dataset_path.as_str()));
            let mut backend = Backend::load_state(program_args.load, &state_dir);

            param.time = backend.state.time;
            param.prev_dt = backend.state.prev_dt;
            builder::copy_to_dataset(
                &backend.state.curr_vertex,
                &backend.state.prev_vertex,
                &mut dataset,
            );

            let mut session = Self {
                program_args,
                sim_args,
                scene,
                backend,
                dataset: Box::new(dataset),
                param: Box::new(param),
                contact_thread: None,
            };
            session.initialize_device()?;
            Ok(session)
        } else {
            // Initialize path: matches the `main.rs` initialization flow.
            let mut backend = Backend::new(scene.make_mesh());
            let mesh = &backend.mesh;
            let face_area = triutils::face_areas(&mesh.vertex, &mesh.mesh.mesh.face);
            let tet_volumes = triutils::tet_volumes(&mesh.vertex, &mesh.mesh.mesh.tet);

            let mut props = scene.make_props(mesh, &face_area, &tet_volumes);

            let time = backend.state.time;
            let temp_constraint = scene.make_constraint(time);

            // Deduplicate edge params and populate non-rod edges.
            let mut edge_param_map: HashMap<EdgeParam, u32> = HashMap::new();
            for (i, param) in props.edge_params.iter().enumerate() {
                edge_param_map.insert(*param, i as u32);
            }

            let mut edge_prop = Vec::new();
            for i in 0..mesh.mesh.mesh.edge.ncols() {
                let rod = mesh.mesh.mesh.edge.column(i);
                let x0 = mesh.vertex.column(rod[0]);
                let x1 = mesh.vertex.column(rod[1]);
                if i < mesh.mesh.mesh.rod_count {
                    edge_prop.push(props.edge[i]);
                } else {
                    let length = (x1 - x0).norm();
                    let mut ghat_sum = 0.0;
                    let mut offset_sum = 0.0;
                    let mut friction_sum = 0.0;
                    let mut area_sum = 0.0;
                    for &j in mesh.mesh.neighbor.edge.face[i].iter() {
                        let face_prop = props.face.get(j).ok_or_else(|| {
                            format!("Invalid face index {j} in edge neighbor list")
                        })?;
                        let face_param = &props.face_params[face_prop.param_index as usize];
                        let area = face_area[j];
                        ghat_sum += area * face_param.ghat;
                        friction_sum += area * face_param.friction;
                        offset_sum += area * face_param.offset;
                        area_sum += area;
                    }
                    assert_gt!(area_sum, 0.0);
                    let ghat = ghat_sum / area_sum;
                    let offset = offset_sum / area_sum;
                    let friction = friction_sum / area_sum;

                    let param = EdgeParam {
                        stiffness: 0.0,
                        bend: 0.0,
                        ghat,
                        offset,
                        friction,
                    };
                    let param_idx = *edge_param_map.entry(param).or_insert_with(|| {
                        let new_idx = props.edge_params.len() as u32;
                        props.edge_params.push(param);
                        new_idx
                    });

                    edge_prop.push(EdgeProp {
                        length,
                        mass: 0.0,
                        fixed: false,
                        param_index: param_idx,
                    });
                }
            }
            props.edge = edge_prop;

            let velocity = scene.get_initial_velocity();
            let dataset = builder::build(&sim_args, mesh, &velocity, &mut props, temp_constraint);
            let param = builder::make_param(&sim_args);

            let mut session = Self {
                program_args,
                sim_args,
                scene,
                backend,
                dataset: Box::new(dataset),
                param: Box::new(param),
                contact_thread: None,
            };
            session.initialize_device()?;
            Ok(session)
        }
    }

    fn initialize_device(&mut self) -> Result<(), String> {
        let ok = unsafe { initialize(self.dataset.as_ref(), self.param.as_ref()) };
        if !ok {
            return Err("failed to initialize backend".to_string());
        }

        if self.program_args.load > 0 && !self.sim_args.disable_contact {
            // Mirror Backend::run load-path initialization.
            self.backend.update_bvh();
            unsafe {
                update_dyn(
                    self.backend.state.dyn_index.as_ptr(),
                    self.backend.state.dyn_offset.as_ptr(),
                );
            }
        }

        if !self.sim_args.disable_contact {
            self.start_contact_thread();
        }

        Ok(())
    }

    fn start_contact_thread(&mut self) {
        let (task_sender, task_receiver) = mpsc::channel();
        let (result_sender, result_receiver) = mpsc::channel();

        std::thread::spawn(move || {
            while let Ok((vertex, face, edge)) = task_receiver.recv() {
                let face = builder::build_bvh(&vertex, Some(&face));
                let edge = builder::build_bvh(&vertex, Some(&edge));
                let vertex = builder::build_bvh::<1>(&vertex, None);
                let _ = result_sender.send(BvhSet { face, edge, vertex });
            }
        });

        self.contact_thread = Some(ContactThread {
            task_sender,
            result_receiver,
            task_sent: false,
        });
    }

    fn maybe_update_bvh_on_new_frame(&mut self) {
        if self.sim_args.disable_contact {
            return;
        }

        let new_frame = (self.backend.state.time * self.sim_args.fps).floor() as i32;
        if new_frame == self.backend.state.curr_frame {
            return;
        }

        self.backend
            .fetch_state(self.dataset.as_ref(), self.param.as_ref());

        if let Some(contact) = self.contact_thread.as_mut() {
            if contact.task_sent {
                match contact.result_receiver.try_recv() {
                    Ok(bvh) => {
                        let n_surface_vert = self.backend.mesh.mesh.mesh.surface_vert_count;
                        let vert: Matrix3xX<f32> = self
                            .backend
                            .state
                            .curr_vertex
                            .columns(0, n_surface_vert)
                            .into_owned();
                        self.backend.bvh = Box::new(Some(bvh));
                        unsafe {
                            update_bvh(self.backend.bvh.as_ref().as_ref().unwrap());
                        }
                        let data = (
                            vert,
                            self.backend.mesh.mesh.mesh.face.clone(),
                            self.backend.mesh.mesh.mesh.edge.clone(),
                        );
                        let _ = contact.task_sender.send(data);
                    }
                    Err(mpsc::TryRecvError::Empty) => {}
                    Err(mpsc::TryRecvError::Disconnected) => {
                        // If the thread died, just stop BVH updates.
                        self.contact_thread = None;
                    }
                }
            } else {
                let n_surface_vert = self.backend.mesh.mesh.mesh.surface_vert_count;
                let vert: Matrix3xX<f32> = self
                    .backend
                    .state
                    .curr_vertex
                    .columns(0, n_surface_vert)
                    .into_owned();
                let data = (
                    vert,
                    self.backend.mesh.mesh.mesh.face.clone(),
                    self.backend.mesh.mesh.mesh.edge.clone(),
                );
                let _ = contact.task_sender.send(data);
                contact.task_sent = true;
            }
        }

        self.backend.state.curr_frame = new_frame;
    }

    /// Executes a single simulation step and returns the latest vertex positions.
    pub fn step_vertices_flat(&mut self) -> Result<Vec<f32>, String> {
        let debug = Self::debug_enabled();
        if debug {
            eprintln!("[ppf inproc] step: t={} frame={}", self.backend.state.time, self.backend.state.curr_frame);
        }
        let constraint = self.scene.make_constraint(self.backend.state.time);
        if debug {
            eprintln!("[ppf inproc] update_constraint");
        }
        unsafe { update_constraint(&constraint) };

        if debug {
            eprintln!("[ppf inproc] maybe_update_bvh_on_new_frame");
        }
        self.maybe_update_bvh_on_new_frame();

        if debug {
            eprintln!("[ppf inproc] update_param");
        }
        self.scene
            .update_param(&self.sim_args, self.backend.state.time, self.param.as_mut());

        let mut result = StepResult::default();
        if debug {
            eprintln!("[ppf inproc] advance");
        }
        unsafe { advance(&mut result) };
        if debug {
            eprintln!("[ppf inproc] advance done success={} time={}", result.success(), result.time);
        }
        if !result.success() {
            return Err("failed to advance".to_string());
        }
        self.backend.state.time = result.time;

        if debug {
            eprintln!("[ppf inproc] fetch_state");
        }
        // Fetch updated state so Blender can display it immediately.
        self.backend
            .fetch_state(self.dataset.as_ref(), self.param.as_ref());
        if debug {
            eprintln!("[ppf inproc] fetch_state done");
        }

        let n = self.backend.mesh.mesh.mesh.vertex_count;
        let mut out = Vec::with_capacity(3 * n);
        for col in self.backend.state.curr_vertex.columns(0, n).column_iter() {
            out.push(col.x);
            out.push(col.y);
            out.push(col.z);
        }
        Ok(out)
    }

    /// Overwrites the current vertex state from a flat xyz buffer.
    ///
    /// This is optional; it lets a host (e.g. Blender) drive the initial condition.
    pub fn set_curr_vertices_flat(&mut self, verts_flat: &[f32]) -> Result<(), String> {
        let n = self.backend.mesh.mesh.mesh.vertex_count;
        if verts_flat.len() != 3 * n {
            return Err(format!(
                "Expected {} floats ({} vertices), got {}",
                3 * n,
                n,
                verts_flat.len()
            ));
        }

        // Important: DO NOT replace `dataset.vertex` CVecs after `initialize()`.
        // The CUDA backend keeps raw pointers into these arrays.
        let expected = n as u32;
        if self.dataset.vertex.curr.size != expected || self.dataset.vertex.prev.size != expected {
            return Err(format!(
                "Dataset vertex buffers have unexpected size: curr={}, prev={}, expected={} (did you change dataset after initialize?)",
                self.dataset.vertex.curr.size,
                self.dataset.vertex.prev.size,
                expected
            ));
        }

        let curr_buf: &mut [Vec3fp] = unsafe {
            std::slice::from_raw_parts_mut(self.dataset.vertex.curr.data, n)
        };
        let prev_buf: &mut [Vec3fp] = unsafe {
            std::slice::from_raw_parts_mut(self.dataset.vertex.prev.data, n)
        };

        for i in 0..n {
            let x = verts_flat[3 * i + 0];
            let y = verts_flat[3 * i + 1];
            let z = verts_flat[3 * i + 2];
            let v = Vec3fp::new(x, y, z);
            curr_buf[i] = v;
            prev_buf[i] = v;
        }

        // Keep the Rust-side cached matrices consistent too.
        let mut curr = Matrix3xX::<f32>::zeros(n);
        for i in 0..n {
            curr[(0, i)] = verts_flat[3 * i + 0];
            curr[(1, i)] = verts_flat[3 * i + 1];
            curr[(2, i)] = verts_flat[3 * i + 2];
        }
        self.backend.state.curr_vertex = curr.clone();
        self.backend.state.prev_vertex = curr;
        Ok(())
    }

    pub fn close(&mut self) {
        // Dropping the channels will stop the contact thread.
        self.contact_thread = None;
    }
}
