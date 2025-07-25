window.addEventListener('DOMContentLoaded', function () {
  const canvas = document.getElementById('renderCanvas');
  const modeIndicator = document.getElementById('modeIndicator');
  const engine = new BABYLON.Engine(canvas, true);

  const createScene = function () {
    const scene = new BABYLON.Scene(engine);

    const camera = new BABYLON.ArcRotateCamera(
      'camera',
      -Math.PI / 2,
      Math.PI / 2.5,
      5,
      BABYLON.Vector3.Zero(),
      scene,
    );
    camera.attachControl(canvas, true);

    const light = new BABYLON.HemisphericLight(
      'light',
      new BABYLON.Vector3(0, 1, 0),
      scene,
    );

    const box = BABYLON.MeshBuilder.CreateBox('box', { size: 1, updatable: true });
    box.position.y = 0.5;
    const ground = BABYLON.MeshBuilder.CreateGround(
      'ground',
      { width: 6, height: 6 },
      scene,
    );
    const sphere = BABYLON.MeshBuilder.CreateSphere('sphere', { diameter: 0.75 });
    sphere.position.y = 1.5;

    let editMode = false;
    const vertexSpheres = [];

    function getVertexGroups(mesh) {
      const positions = mesh.getVerticesData(BABYLON.VertexBuffer.PositionKind);
      const groups = [];
      for (let i = 0; i < positions.length; i += 3) {
        const p = new BABYLON.Vector3(positions[i], positions[i + 1], positions[i + 2]);
        let found = groups.find(g => g.pos.equalsWithEpsilon(p));
        if (!found) {
          found = { pos: p.clone(), indices: [] };
          groups.push(found);
        }
        found.indices.push(i);
      }
      return groups;
    }

    function createVertexSpheres(mesh) {
      const groups = getVertexGroups(mesh);
      groups.forEach(g => {
        const vs = BABYLON.MeshBuilder.CreateSphere('v', { diameter: 0.1 }, scene);
        vs.position.copyFrom(g.pos);
        vs.isVisible = false;
        const drag = new BABYLON.PointerDragBehavior();
        drag.useObjectOrientationForDragging = false;
        vs.addBehavior(drag);
        drag.onDragObservable.add(ev => {
          g.pos.copyFrom(ev.dragPlanePoint);
          vs.position.copyFrom(g.pos);
          const positions = mesh.getVerticesData(BABYLON.VertexBuffer.PositionKind);
          g.indices.forEach(idx => {
            positions[idx] = g.pos.x;
            positions[idx + 1] = g.pos.y;
            positions[idx + 2] = g.pos.z;
          });
          mesh.updateVerticesData(BABYLON.VertexBuffer.PositionKind, positions);
        });
        vertexSpheres.push(vs);
      });
    }

    createVertexSpheres(box);

    function setMode(isEdit) {
      editMode = isEdit;
      modeIndicator.textContent = editMode ? 'Edit Mode' : 'Object Mode';
      vertexSpheres.forEach(s => (s.isVisible = editMode));
    }

    function addPrimitive(key) {
      switch (key) {
        case '1':
          BABYLON.MeshBuilder.CreateBox('box' + Date.now(), { size: 1 }, scene).position.y = 0.5;
          break;
        case '2':
          BABYLON.MeshBuilder.CreateSphere('sphere' + Date.now(), { diameter: 1 }, scene).position.y = 0.5;
          break;
        case '3':
          BABYLON.MeshBuilder.CreateCylinder('cyl' + Date.now(), { height: 1, diameter: 1 }, scene).position.y = 0.5;
          break;
      }
    }

    window.addEventListener('keydown', e => {
      if (e.key === 'Tab') {
        e.preventDefault();
        setMode(!editMode);
      } else if (!editMode) {
        addPrimitive(e.key);
      }
    });

    let angle = 0;
    scene.registerBeforeRender(function () {
      box.rotation.y += 0.01;
      angle += 0.02;
      sphere.position.x = Math.cos(angle) * 2;
      sphere.position.z = Math.sin(angle) * 2;
    });

    scene.onPointerObservable.add(pointerInfo => {
      if (pointerInfo.type === BABYLON.PointerEventTypes.POINTERPICK) {
        const mesh = pointerInfo.pickInfo && pointerInfo.pickInfo.pickedMesh;
        if (mesh) {
          const mat =
            mesh.material || new BABYLON.StandardMaterial('mat', scene);
          mesh.material = mat;
          mat.diffuseColor = new BABYLON.Color3(
            Math.random(),
            Math.random(),
            Math.random(),
          );
        }
      }
    });

    return scene;
  };

  const scene = createScene();

  engine.runRenderLoop(function () {
    scene.render();
  });

  window.addEventListener('resize', function () {
    engine.resize();
  });
});
