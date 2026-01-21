"""Plug module for Maya core functionalities."""

from maya import cmds
from maya.api import OpenMaya

from .registry import resolve

class Plug:
    """Represents an attribute plug on a Maya node."""
    _VECTOR_TYPES = frozenset({
        OpenMaya.MFn.kAttribute3Double,  # double3
        OpenMaya.MFn.kAttribute3Float,  # float3
        OpenMaya.MFn.kAttribute2Double,  # double2
        OpenMaya.MFn.kAttribute2Float,  # float2
        OpenMaya.MFn.kAttribute3Short,  # short3
        OpenMaya.MFn.kAttribute3Int,  # long3
    })

    _SCALAR_TYPES = frozenset({
        OpenMaya.MFn.kNumericAttribute,  # Bool, Float, Int, Byte, Short
        OpenMaya.MFn.kEnumAttribute,  # Enums
        OpenMaya.MFn.kUnitAttribute,  # Time, Angle, Distance
        OpenMaya.MFn.kDoubleLinearAttribute,  # Time, Angle, Distance
    })

    def __init__(self, node, attr: str):
        """Initialize a Plug for the given node and attribute name."""
        self._node = node
        self._attr = attr
        self._mplug = None # lazy init

    @property
    def attr(self):
        """The attribute name."""
        return self._attr

    @property
    def path(self):
        """The full attribute path."""
        return f"{self._node.name}.{self._attr}"

    @property
    def node(self):
        """The node this plug belongs to."""
        return self._node

    @property
    def mplug(self):
        """The MPlug representation of this attribute."""
        if self._mplug is None:
            self._mplug = self._find_plug()
            if self._mplug is None:
                raise RuntimeError(
                    f"Attribute '{self._node.name}.{self._attr}' not found.")

        if self._mplug.isNull:
            # Attempt to re-fetch in case it was deleted and recreated (Undo/Redo scenarios)
            self._mplug = self._find_plug()
            if self._mplug is None or self._mplug.isNull:
                raise RuntimeError(
                    f"Attribute '{self._node.name}.{self._attr}' acts invalid/deleted.")

        return self._mplug

    @property
    def value(self):
        """Get the value of the attribute."""
        return self.get()

    @value.setter
    def value(self, new_value):
        """Set the value of the attribute."""
        self.set(new_value)

    @property
    def visible(self) -> bool:
        """Check if the attribute is visible in the channelbox."""
        # An attribute is considered visible if it is either keyable or in the channel
        # box.
        # _keyable = cmds.getAttr(self.path, keyable=True)
        _keyable = self.mplug.isKeyable
        _channelbox = cmds.getAttr(self.path, channelBox=True)
        return _keyable or _channelbox

    @visible.setter
    def visible(self, state: bool) -> None:
        """Set the visibility of the attribute in the channelbox.

        Args:
            state (bool): True to show the attribute, False to hide.
        """
        # _keyable = cmds.getAttr(self.path, keyable=True)
        _keyable = self.mplug.isKeyable
        if not state:
            cmds.setAttr(self.path, edit=True, keyable=False, channelBox=False)
            return
        cmds.setAttr(self.path, edit=True, keyable=_keyable, channelBox=state)

    @property
    def keyable(self) -> bool:
        """Check if the attribute is keyable."""
        return self.mplug.isKeyable

    @keyable.setter
    def keyable(self, state: bool) -> None:
        """Set the keyable state of the attribute.

        Args:
            state (bool): True to make the attribute keyable,
                False to make it non-keyable.
        """
        # if its not explicitly hidden, we expose it in the channel box when making it
        # keyable
        if cmds.getAttr(self.path, channelBox=True):
            cmds.setAttr(self.path, edit=True, keyable=state)
        else:
            cmds.setAttr(self.path, edit=True, keyable=state, channelBox=not state)

    @property
    def locked(self) -> bool:
        """Check if the attribute is locked."""
        return self.mplug.isLocked

    @locked.setter
    def locked(self, state: bool) -> None:
        """Set the lock state of the attribute.

        Args:
            state (bool): True to lock the attribute, False to unlock.
        """
        cmds.setAttr(self.path, edit=True, lock=state)

    @property
    def children(self):
        """If the plug is a compund attribute, return its child plugs."""
        children = cmds.listAttr(self.path, multi=True)
        if not children:
            return []
        return [Plug(self._node, f"{child}") for child in children if child != self.attr]

    @property
    def type(self):
        """The attribute type as a string."""
        return self.mplug.attribute().apiTypeStr

    def exists(self):
        """Check if the attribute exists."""
        return cmds.attributeQuery(self.attr, node=self._node.name, exists=True)

    def create(self, **kwargs):
        """Add a new attribute to the node.

        Args:
            **kwargs: Additional keyword arguments to pass to cmds.addAttr.
        """
        cmds.addAttr(self._node.long_name, longName=self.attr, **kwargs)

    def delete(self):
        """Delete an attribute from the node."""
        cmds.deleteAttr(f"{self._node.long_name}.{self.attr}")

    def get(self, **kwargs):
        """Get the value of the attribute.

        Args:
            **kwargs: Additional keyword arguments to pass to cmds.getAttr.
        """
        return cmds.getAttr(self.path, **kwargs)

    def set(self, value, **kwargs):
        """Set the value of the attribute.

        Args:
            value: The value to set. Can be a single value or a list/tuple for
                multi-value attributes.
            **kwargs: Additional keyword arguments to pass to cmds.setAttr.
        """
        _type = kwargs.pop("type", None)
        if isinstance(value, (list, tuple)):
            # if there are 16 values, and the type not explicit assume it's a 4x4 matrix
            if len(value) == 16 and not _type:
                cmds.setAttr(self.path, *value, type="matrix", **kwargs)
            else:
                cmds.setAttr(self.path, *value, **kwargs)
        elif isinstance(value, (float, int, bool)):
            cmds.setAttr(self.path, value, **kwargs)
        elif isinstance(value, str):
            _type = _type or "string"
            cmds.setAttr(self.path, value, type=_type, **kwargs)
        else:
            raise TypeError(f"Unsupported type for setting attribute: {type(value)}")

    # def as_api_plug(self):
    #     """Get the attribute as an OpenMaya MPlug."""
    #     selection_list = OpenMaya.MSelectionList()
    #     try:
    #         selection_list.add(self.path)
    #         return selection_list.getPlug(0)
    #     except RuntimeError:
    #         return None

    def _find_plug(self):
        """Get the attribute as an OpenMaya MPlug."""
        selection_list = OpenMaya.MSelectionList()
        try:
            selection_list.add(self.path)
            return selection_list.getPlug(0)
        except RuntimeError:
            return None

    def rename(self, new_attr_name):
        """Rename the attribute.

        Args:
            new_attr_name (str): The new name for the attribute.
        """
        cmds.renameAttr(self.path, new_attr_name)
        self._attr = new_attr_name

    def connect(self, other: "Plug", force: bool = True) -> None:
        """Connect this plug to another plug.

        Args:
            other (Plug): The plug to connect to.
            force (bool): Whether to force the connection, breaking existing
                connections if necessary.
        """
        cmds.connectAttr(self.path, other.path, force=force)

    def disconnect(self, other=None):
        """Disconnect this plug from another plug, or from its source if no
        plug is given.

        Args:
            other (Plug, optional): The plug to disconnect from. If None,
                disconnects from the source connection.
        """
        if other:
            cmds.disconnectAttr(self.path, other.path)
        else:
            sources = cmds.listConnections(self.path, plugs=True, source=True)
            if sources:
                cmds.disconnectAttr(sources[0], self.path)

    def get_input(self, plug=False):
        """List incoming connections to this plug.

        Returns:
            list of Plug: A list of Plug instances representing the incoming
                connections.
        """
        connections = cmds.listConnections(
            self.path, plugs=True, source=True, destination=False
        )
        if not connections:
            return None

        input_plug = connections[0]
        # input_plugs = raw_inputs[::2] if raw_inputs else []
        splits = input_plug.split(".")
        node = resolve(splits[0])
        if not plug:
            return node
        plug_parts = splits[1:]
        return Plug(node, ".".join(plug_parts))

        # return [Plug(self._node, src.split('.', 1)[1]) for src in sources]

    def list_inputs(self, plugs=False):
        """List incoming connections to this plug.

        Returns:
            list of Plug: A list of Plug instances representing the incoming
                connections.
        """
        input_plugs = cmds.listConnections(
            self.path, plugs=True, source=True, destination=False
        )
        inputs = []
        if not input_plugs:
            return inputs

        for plug in input_plugs:
            splits = plug.split(".")
            node = resolve(splits[0])
            if not plugs:
                inputs.append(node)
            else:
                plug_parts = splits[1:]
                inputs.append(Plug(node, ".".join(plug_parts)))
        return inputs

    def list_outputs(self, plugs=False):
        """List outgoing connections from this plug.

        Returns:
            list of Plug: A list of Plug instances representing the outgoing
                connections.
        """
        output_plugs = cmds.listConnections(
            self.path, plugs=True, source=False, destination=True
        )
        outputs = []
        if not output_plugs:
            return outputs

        for plug in output_plugs:
            splits = plug.split(".")
            node = resolve(splits[0])
            if not plugs:
                outputs.append(node)
            else:
                plug_parts = splits[1:]
                outputs.append(Plug(node, ".".join(plug_parts)))
        return outputs

    def lock(self):
        """Lock the attribute."""
        self.locked = True

    def unlock(self):
        """Unlock the attribute."""
        self.locked = False

    def __getitem__(self, attr):
        """Get a child plug (for compound attributes).

        Args:
            attr (str): The child attribute name.
        """
        return Plug(self._node, f"{self.attr}.{attr}")

    def __rshift__(self, other: "Plug") -> "Plug":
        """Connect self to other using `>>` operator and return the
        right‑hand side for chaining.

        Args:
            other (Plug): The plug to connect to.
        """
        if not isinstance(other, Plug):
            raise TypeError(f"Right operand must be a Plug, got {type(other)}")
        self.connect(other, force=True)
        return other

    def __lshift__(self, other: "Plug") -> "Plug":
        """Connect other to self using `<<` operator (reverse of `>>`).

        Args:
            other (Plug): The plug to connect from.

        Returns:
            Plug: Returns self for chaining.
        """
        if not isinstance(other, Plug):
            raise TypeError(f"Right operand must be a Plug, got {type(other)}")
        other.connect(self, force=True)
        return self

    def __floordiv__(self, other: "Plug") -> None:
        """Disconnect self from other using `//` operator.

        Args:
            other (Plug): The plug to disconnect from.

        Returns:
            None: No value is returned.
        """
        if not isinstance(other, Plug):
            raise TypeError(f"Right operand must be a Plug, got {type(other)}")
        self.disconnect(other)
        return None

    # === Mathematical Operators ===

    def _is_compound_numeric(self) -> bool:
        """Check if this plug is a compound attribute with numeric children.

        Returns:
            bool: True if compound with 2-3 numeric children (e.g., double3, float3).
        """
        return self.mplug.attribute().apiType() in self._VECTOR_TYPES

    def _is_scalar_numeric(self) -> bool:
        """
        True if attribute is a single math-able value (bool, enum, int, float, time).
        Safe to get value directly.
        """
        return self.mplug.attribute().apiType() in self._SCALAR_TYPES

    def _create_plug(self, node_name: str, attr_name: str) -> "Plug":
        """Create a Plug instance for the given node and attribute.

        Args:
            node_name (str): The name of the node.
            attr_name (str): The attribute name.

        Returns:
            Plug: A new Plug instance.
        """
        node_wrapper = resolve(node_name)
        return Plug(node_wrapper, attr_name)

    # --- Single Value Math Nodes ---

    def _create_add_node_single(self, other) -> "Plug":
        """Create an addDL node for single-value addition.

        Args:
            other: The right-hand operand (Plug or numeric value).

        Returns:
            Plug: The output plug of the addDL node.
        """
        node = cmds.createNode("addDL", name="addDL#")

        # Connect input1 (left operand - self)
        cmds.connectAttr(self.path, f"{node}.input1", force=True)

        # Connect or set input2 (right operand - other)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.input2", force=True)
        elif isinstance(other, (int, float)):
            cmds.setAttr(f"{node}.input2", float(other))
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, "output")

    def _create_subtract_node_single(self, other) -> "Plug":
        """Create a subtract node for single-value subtraction.

        Args:
            other: The right-hand operand (Plug or numeric value).

        Returns:
            Plug: The output plug of the subtract node.
        """
        node = cmds.createNode("subtract", name="subtract#")

        # Connect input1 (left operand - self)
        cmds.connectAttr(self.path, f"{node}.input1", force=True)

        # Connect or set input2 (right operand - other)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.input2", force=True)
        elif isinstance(other, (int, float)):
            cmds.setAttr(f"{node}.input2", float(other))
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, "output")

    def _create_multiply_node_single(self, other) -> "Plug":
        """Create a multDL node for single-value multiplication.

        Args:
            other: The right-hand operand (Plug or numeric value).

        Returns:
            Plug: The output plug of the multDL node.
        """
        node = cmds.createNode("multDL", name="multDL#")

        # Connect input1 (left operand - self)
        cmds.connectAttr(self.path, f"{node}.input1", force=True)

        # Connect or set input2 (right operand - other)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.input2", force=True)
        elif isinstance(other, (int, float)):
            cmds.setAttr(f"{node}.input2", float(other))
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, "output")

    def _create_divide_node_single(self, other) -> "Plug":
        """Create a divide node for single-value division.

        Args:
            other: The right-hand operand (Plug or numeric value).

        Returns:
            Plug: The output plug of the divide node.
        """
        node = cmds.createNode("divide", name="divide#")

        # Connect input1 (left operand - self / dividend)
        cmds.connectAttr(self.path, f"{node}.input1", force=True)

        # Connect or set input2 (right operand - other / divisor)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.input2", force=True)
        elif isinstance(other, (int, float)):
            cmds.setAttr(f"{node}.input2", float(other))
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, "output")

    def _create_power_node_single(self, other) -> "Plug":
        """Create a power node for single-value power operation.

        Args:
            other: The right-hand operand (Plug or numeric value) for the exponent.

        Returns:
            Plug: The output plug of the power node.
        """
        node = cmds.createNode("power", name="power#")

        # Connect input (left operand - self / base)
        cmds.connectAttr(self.path, f"{node}.input", force=True)

        # Connect or set exponent (right operand - other)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.exponent", force=True)
        elif isinstance(other, (int, float)):
            cmds.setAttr(f"{node}.exponent", float(other))
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, "output")

    def _create_modulo_node_single(self, other) -> "Plug":
        """Create a modulo node for single-value modulo operation.

        Args:
            other: The right-hand operand (Plug or numeric value) for the modulus.

        Returns:
            Plug: The output plug of the modulo node.
        """
        node = cmds.createNode("modulo", name="modulo#")

        # Connect input (left operand - self / dividend)
        cmds.connectAttr(self.path, f"{node}.input", force=True)

        # Connect or set modulus (right operand - other)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.modulus", force=True)
        elif isinstance(other, (int, float)):
            cmds.setAttr(f"{node}.modulus", float(other))
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, "output")

    # --- Compound Value Math Nodes ---

    def _create_plus_minus_node_compound(
        self, other, operation: int, operation_name: str
    ) -> "Plug":
        """Create a plusMinusAverage node for compound add/subtract operations.

        Uses compound-to-compound connections for better performance.

        Args:
            other: The right-hand operand (Plug or numeric value).
            operation (int): The operation enum value (1=sum, 2=subtract).
            operation_name (str): The name of the operation for node naming.

        Returns:
            Plug: The output3D plug of the plusMinusAverage node.
        """
        node = cmds.createNode(
            "plusMinusAverage", name=f"plusMinusAverage_{operation_name}#"
        )
        cmds.setAttr(f"{node}.operation", operation)

        # Connect compound input3D[0] (left operand - self)
        cmds.connectAttr(self.path, f"{node}.input3D[0]", force=True)

        # Connect or set compound input3D[1] (right operand - other)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.input3D[1]", force=True)
        elif isinstance(other, (int, float)):
            # Set all three components to the same value
            value = float(other)
            cmds.setAttr(f"{node}.input3D[1]", value, value, value, type="double3")
        elif isinstance(other, (list, tuple)) and len(other) == 3:
            cmds.setAttr(
                f"{node}.input3D[1]",
                float(other[0]), float(other[1]), float(other[2]),
                type="double3"
            )
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, "output3D")

    def _create_multiply_divide_node_compound(
        self, other, operation: int, operation_name: str
    ) -> "Plug":
        """Create a multiplyDivide node for compound multiply/divide/power.

        Uses compound-to-compound connections for better performance.

        Args:
            other: The right-hand operand (Plug or numeric value).
            operation (int): The operation enum (1=multiply, 2=divide, 3=power).
            operation_name (str): The name of the operation for node naming.

        Returns:
            Plug: The output plug of the multiplyDivide node.
        """
        node = cmds.createNode(
            "multiplyDivide", name=f"multiplyDivide_{operation_name}#"
        )
        cmds.setAttr(f"{node}.operation", operation)

        # Connect compound input1 (left operand - self)
        cmds.connectAttr(self.path, f"{node}.input1", force=True)

        # Connect or set compound input2 (right operand - other)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.input2", force=True)
        elif isinstance(other, (int, float)):
            # Set all three components to the same value
            value = float(other)
            cmds.setAttr(f"{node}.input2", value, value, value, type="double3")
        elif isinstance(other, (list, tuple)) and len(other) == 3:
            cmds.setAttr(
                f"{node}.input2",
                float(other[0]), float(other[1]), float(other[2]),
                type="double3"
            )
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, "output")

    # --- Public Operator Methods ---

    def __add__(self, other) -> "Plug":
        """Add two plugs or a plug and a numeric value using `+` operator.

        For single values, creates an addDL node.
        For compound values (double3/float3), creates a plusMinusAverage node.

        Args:
            other: A Plug or numeric value to add.

        Returns:
            Plug: The output plug of the created node.
        """
        if self._is_compound_numeric():
            return self._create_plus_minus_node_compound(
                other, operation=1, operation_name="add"
            )
        elif self._is_scalar_numeric():
            return self._create_add_node_single(other)
        else:
            raise TypeError(
                f"Addition not supported for attribute type: "
                f"{self.type}"
            )

    def __radd__(self, other) -> "Plug":
        """Handle reversed addition (numeric + plug).

        Args:
            other: A numeric value to add.

        Returns:
            Plug: The output plug of the created node.
        """
        # Addition is commutative, so we can just call __add__
        return self.__add__(other)

    def __sub__(self, other) -> "Plug":
        """Subtract a plug or numeric value from this plug using `-` operator.

        For single values, creates a subtract node.
        For compound values (double3/float3), creates a plusMinusAverage node.

        Args:
            other: A Plug or numeric value to subtract.

        Returns:
            Plug: The output plug of the created node.
        """
        if self._is_compound_numeric():
            return self._create_plus_minus_node_compound(
                other, operation=2, operation_name="subtract"
            )
        elif self._is_scalar_numeric():
            return self._create_subtract_node_single(other)
        else:
            raise TypeError(
                f"Subtraction not supported for attribute type: "
                f"{self.type}"
            )

    def __rsub__(self, other) -> "Plug":
        """Handle reversed subtraction (numeric - plug).

        Args:
            other: A numeric value to subtract from.

        Returns:
            Plug: The output plug of the created node.
        """
        if self._is_compound_numeric():
            # For compound: create node with other as first input
            node = cmds.createNode(
                "plusMinusAverage", name="plusMinusAverage_subtract#"
            )
            cmds.setAttr(f"{node}.operation", 2)  # Subtract

            if isinstance(other, (int, float)):
                value = float(other)
                cmds.setAttr(
                    f"{node}.input3D[0]", value, value, value, type="double3"
                )
            elif isinstance(other, (list, tuple)) and len(other) == 3:
                cmds.setAttr(
                    f"{node}.input3D[0]",
                    float(other[0]), float(other[1]), float(other[2]),
                    type="double3"
                )
            else:
                raise TypeError(
                    f"Left operand must be a numeric value, got {type(other)}"
                )
            cmds.connectAttr(self.path, f"{node}.input3D[1]", force=True)
            return self._create_plug(node, "output3D")
        elif self._is_scalar_numeric():
            # Single value: create subtract node with other as first input
            node = cmds.createNode("subtract", name="subtract#")
            if isinstance(other, (int, float)):
                cmds.setAttr(f"{node}.input1", float(other))
            else:
                raise TypeError(
                    f"Left operand must be a numeric value, got {type(other)}"
                )
            cmds.connectAttr(self.path, f"{node}.input2", force=True)
            return self._create_plug(node, "output")
        else:
            raise TypeError(
                f"Subtraction not supported for attribute type: "
                f"{self.type}"
            )

    def __mul__(self, other) -> "Plug":
        """Multiply two plugs or a plug and a numeric value using `*` operator.

        For single values, creates a multDL node.
        For compound values (double3/float3), creates a multiplyDivide node.

        Args:
            other: A Plug or numeric value to multiply.

        Returns:
            Plug: The output plug of the created node.
        """
        if self._is_compound_numeric():
            return self._create_multiply_divide_node_compound(
                other, operation=1, operation_name="multiply"
            )
        elif self._is_scalar_numeric():
            return self._create_multiply_node_single(other)
        else:
            raise TypeError(
                f"Multiplication not supported for attribute type: "
                f"{self.type}"
            )

    def __rmul__(self, other) -> "Plug":
        """Handle reversed multiplication (numeric * plug).

        Args:
            other: A numeric value to multiply.

        Returns:
            Plug: The output plug of the created node.
        """
        # Multiplication is commutative, so we can just call __mul__
        return self.__mul__(other)

    def __truediv__(self, other) -> "Plug":
        """Divide this plug by a plug or numeric value using `/` operator.

        For single values, creates a divide node.
        For compound values (double3/float3), creates a multiplyDivide node.

        Args:
            other: A Plug or numeric value to divide by.

        Returns:
            Plug: The output plug of the created node.
        """
        if self._is_compound_numeric():
            return self._create_multiply_divide_node_compound(
                other, operation=2, operation_name="divide"
            )
        elif self._is_scalar_numeric():
            return self._create_divide_node_single(other)
        else:
            raise TypeError(
                f"Division not supported for attribute type: "
                f"{self.type}"
            )

    def __rtruediv__(self, other) -> "Plug":
        """Handle reversed division (numeric / plug).

        Args:
            other: A numeric value to divide.

        Returns:
            Plug: The output plug of the created node.
        """
        if self._is_compound_numeric():
            # For compound: create node with other as first input
            node = cmds.createNode("multiplyDivide", name="multiplyDivide_divide#")
            cmds.setAttr(f"{node}.operation", 2)  # Divide

            if isinstance(other, (int, float)):
                value = float(other)
                cmds.setAttr(f"{node}.input1", value, value, value, type="double3")
            elif isinstance(other, (list, tuple)) and len(other) == 3:
                cmds.setAttr(
                    f"{node}.input1",
                    float(other[0]), float(other[1]), float(other[2]),
                    type="double3"
                )
            else:
                raise TypeError(
                    f"Left operand must be a numeric value, got {type(other)}"
                )
            cmds.connectAttr(self.path, f"{node}.input2", force=True)
            return self._create_plug(node, "output")
        elif self._is_scalar_numeric():
            # Single value: create divide node with other as first input
            node = cmds.createNode("divide", name="divide#")
            if isinstance(other, (int, float)):
                cmds.setAttr(f"{node}.input1", float(other))
            else:
                raise TypeError(
                    f"Left operand must be a numeric value, got {type(other)}"
                )
            cmds.connectAttr(self.path, f"{node}.input2", force=True)
            return self._create_plug(node, "output")
        else:
            raise TypeError(
                f"Division not supported for attribute type: "
                f"{self.type}"
            )

    def __pow__(self, other) -> "Plug":
        """Raise plug to a power using `**` operator.

        For single values, creates a power node.
        For compound values (double3/float3), creates a multiplyDivide node.

        Args:
            other: A Plug or numeric value for the exponent.

        Returns:
            Plug: The output plug of the created node.
        """
        if self._is_compound_numeric():
            return self._create_multiply_divide_node_compound(
                other, operation=3, operation_name="power"
            )
        elif self._is_scalar_numeric():
            return self._create_power_node_single(other)
        else:
            raise TypeError(
                f"Power operation not supported for attribute type: "
                f"{self.type}"
            )

    def __rpow__(self, other) -> "Plug":
        """Handle reversed power (numeric ** plug).

        Args:
            other: A numeric value as the base.

        Returns:
            Plug: The output plug of the created node.
        """
        if self._is_compound_numeric():
            # For compound: create node with other as base (input1)
            node = cmds.createNode("multiplyDivide", name="multiplyDivide_power#")
            cmds.setAttr(f"{node}.operation", 3)  # Power

            if isinstance(other, (int, float)):
                value = float(other)
                cmds.setAttr(f"{node}.input1", value, value, value, type="double3")
            elif isinstance(other, (list, tuple)) and len(other) == 3:
                cmds.setAttr(
                    f"{node}.input1",
                    float(other[0]), float(other[1]), float(other[2]),
                    type="double3"
                )
            else:
                raise TypeError(
                    f"Left operand must be a numeric value, got {type(other)}"
                )
            cmds.connectAttr(self.path, f"{node}.input2", force=True)
            return self._create_plug(node, "output")

        elif self._is_scalar_numeric():
            # Single value: create power node with other as base
            node = cmds.createNode("power", name="power#")
            if isinstance(other, (int, float)):
                cmds.setAttr(f"{node}.input", float(other))
            else:
                raise TypeError(
                    f"Left operand must be a numeric value, got {type(other)}"
                )
            cmds.connectAttr(self.path, f"{node}.exponent", force=True)
            return self._create_plug(node, "output")
        else:
            raise TypeError(
                f"Power operation not supported for attribute type: "
                f"{self.type}"
            )

    def __mod__(self, other) -> "Plug":
        """Compute modulo using `%` operator.

        Creates a modulo node. Only supports single values.

        Args:
            other: A Plug or numeric value for the divisor (modulus).

        Returns:
            Plug: The output plug of the modulo node.
        """
        # Modulo only supports single values
        return self._create_modulo_node_single(other)

    def __rmod__(self, other) -> "Plug":
        """Handle reversed modulo (numeric % plug).

        Args:
            other: A numeric value as the dividend.

        Returns:
            Plug: The output plug of the modulo node.
        """
        node = cmds.createNode("modulo", name="modulo#")

        # For reversed: other % self, so other goes to input
        if isinstance(other, (int, float)):
            cmds.setAttr(f"{node}.input", float(other))
        else:
            raise TypeError(
                f"Left operand must be a numeric value, got {type(other)}"
            )
        cmds.connectAttr(self.path, f"{node}.modulus", force=True)

        return self._create_plug(node, "output")

    def __repr__(self):
        """Return a debug-friendly representation."""
        return f"<Plug '{self.path}'>"

